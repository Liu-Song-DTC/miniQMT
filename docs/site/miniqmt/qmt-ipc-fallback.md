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

推荐在大QMT中使用模型交易入口部署 `qmt_trade_executor.py`。正常日志应类似：

```text
[11:56:40.467] [TEST_ACC_2] snapshot xttrader: total=13356 positions=1 via asset=StockAccount pos=StockAccount
[11:56:40.482] tick ok accounts=2 ticks=1
```

如果看到连续高频 `tick start/tick done`，说明运行的仍是旧脚本，应重新粘贴最新版本。

## 风险控制

- 下单前策略端检查 `heartbeat.json`，大QMT离线时快速失败。
- 大QMT端处理 `processing/` 超龄文件时写 `error` 回执并清理，不重发订单。
- `done/` 目录按保留时间归档到 `done_archive/`，避免长期运行膨胀。
- 外部交易 API 调用都有超时保护，避免 QMT API 偶发卡死拖住主循环。

## 调试顺序

1. 确认 `heartbeat.json` 持续更新。
2. 确认两个账号都生成 `account.json`，且 `source=xttrader`。
3. 确认持仓字段可信：无零股伪持仓，休盘参考价可反推。
4. 用不会成交的低风险限价单验证 `pending -> processing -> done`。
5. 再做最小数量、有效价格的真实下单验证。
