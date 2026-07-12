# 大QMT文件 IPC Fallback

大QMT文件 IPC 是 `easy_qmt_trader` 直连失效时的交易降级通道：miniQMT 策略端把订单写入 `C:\QuantIPC\{account_id}\orders\pending`，大QMT 内置 Python 脚本 `qmt_trade_executor.py` 读取后用大QMT授权执行下单，并把账户快照和成交回执写回共享目录。

## 适用场景

| 场景 | 是否适用 |
|------|----------|
| 券商收紧 miniQMT `xttrader` 权限 | 适用 |
| 大QMT客户端已登录并具备交易授权 | 适用 |
| 多账号同机隔离运行 | 适用 |
| 高频、打板、tick级抢单 | 不适用 |

## 已验证能力

实机调试确认：

- 模型交易模式会把 `get_trade_detail_data`、`passorder`、`cancel` 注入到 `globals()`。
- `ContextInfo` 主要提供行情和上下文能力，没有发现 `order_stock`、`query_stock_asset`、`cancel_order` 等交易方法。
- `xttrader + StockAccount` 可用于只读快照，并作为下单首选参数形式。
- 休盘时资产字段可能为 0，但持仓仍可返回，需要快照层做数据清洗。
- 光大金阳光 QMT 的“模型交易”入口在非交易日可能只触发一次策略回调；当前 executor 在 `init()` 中进入前台循环，持续轮询 IPC。
- 大QMT 策略容器可能在回调返回后回收后台线程，因此不能把后台 worker 当作主要保活方案。

## 目录约定

```text
C:\QuantIPC\
  TEST_ACC_2\
    config.json
    status\
      heartbeat.json
      account.json
    orders\
      pending\
      processing\
      done\
      done_archive\
    cancel\
```

`config.json` 由策略端创建，至少包含：

```json
{
  "account_id": "TEST_ACC_2",
  "account_type": "STOCK",
  "qmt_path": "C:/QMT1/userdata_mini"
}
```

## 快照口径

`account.json` 由大QMT端写入。当前口径：

- `source` 标识来源，优先 `xttrader`，失败时 fallback 到 `vba`。
- 过滤 `volume<=0` 的伪持仓。
- `market_price=0` 且 `market_value>0` 时按 `market_value / volume` 反推参考价。
- `total_asset<=0` 但有市值时，兜底为 `available + market_value`。

示例：

```json
{
  "timestamp": "2026-07-12 11:56:40",
  "account_id": "TEST_ACC_2",
  "source": "xttrader",
  "total_asset": 13356.0,
  "available": 0.0,
  "market_value": 13356.0,
  "positions": [
    {
      "stock": "600509.SH",
      "volume": 1800,
      "available": 1800,
      "cost": 6.914,
      "market_price": 7.42,
      "market_value": 13356.0
    }
  ]
}
```

## 运行与日志

推荐在大QMT中使用模型交易入口部署 `qmt_trade_executor.py`。若界面里没有“定时运行”选项，直接使用“模型交易/实盘/运行”，不要勾选“启动本地 python”。正常日志应类似：

```text
[11:56:39.900] foreground loop started by init pid=12345 interval=1.000s root=C:\QuantIPC
[11:56:40.467] [TEST_ACC_2] snapshot xttrader: total=13356 positions=1 via asset=StockAccount pos=StockAccount
[11:56:40.482] tick ok accounts=2 ticks=1 worker=False
```

如果看到连续高频 `tick start/tick done`，说明运行的仍是旧脚本，应重新粘贴最新版本。

如果每次手动运行只看到一次 `tick ok accounts=... ticks=1`，之后 `heartbeat.json` 不再刷新，通常不是交易 API 卡死，而是旧版仍在依赖后台线程。请确认已更新到带 `foreground loop started by init` 的新版脚本，并重新编译、保存、运行。

如果日志里继续新增 `worker start requested by top-level` 或旧格式临时文件 `heartbeat.json.<pid>.tmp`，通常说明大QMT里仍有旧实例残留。应先停止策略，必要时重启大QMT客户端，再运行最新版脚本。

验证通过的文件状态：

- `C:\QuantIPC\{account_id}\status\heartbeat.json` 修改时间持续贴近当前时间。
- `C:\QuantIPC\{account_id}\status\account.json` 周期更新；休盘时资产字段可能为 0，但持仓市值应能正常返回或兜底。
- `tick ok accounts=... ticks=...` 中的 `ticks` 持续递增。
- 在模型交易前台循环形态下，`worker=False` 是正常状态；它表示没有额外后台 worker 参与保活。

## 风险控制

- 下单前策略端检查 `heartbeat.json`，大QMT离线时快速失败。
- 大QMT端处理 `processing/` 超龄文件时写 `error` 回执并清理，不重发订单。
- `done/` 目录按保留时间归档到 `done_archive/`，避免长期运行膨胀。
- 外部交易 API 调用都有超时保护，避免 QMT API 偶发卡死拖住主循环。
- 大QMT端写 `done/`、`status/account.json`、`status/heartbeat.json` 时使用唯一临时文件名和短重试，降低 Windows 文件锁导致的 `WinError 32` 风险。

## 调试顺序

1. 确认 `heartbeat.json` 持续更新。
2. 确认两个账号都生成 `account.json`，且 `source=xttrader`。
3. 确认持仓字段可信：无零股伪持仓，休盘参考价可反推。
4. 用不会成交的低风险限价单验证 `pending -> processing -> done`。
5. 再做最小数量、有效价格的真实下单验证。
