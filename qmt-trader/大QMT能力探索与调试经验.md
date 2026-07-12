# 大QMT能力探索与调试经验

本文记录 2026-07-12 对 `qmt_trade_executor.py` 的实机调试结论，用于后续开发和排障。

## 当前确认的能力边界

| 项目 | 结论 |
|------|------|
| 推荐入口 | 模型交易 `init(ContextInfo)` / `handlebar(ContextInfo)` |
| 可用内置交易符号 | `get_trade_detail_data`、`passorder`、`cancel` 位于 `globals()` |
| `ContextInfo` 能力 | 主要是行情、画图、订阅、回测上下文；未发现 `query_stock_asset`、`order_stock`、`cancel_order` 等交易方法 |
| 只读快照首选 | `xttrader + StockAccount` |
| VBA 快照定位 | fallback；休盘或账号上下文不匹配时可能返回空 |
| 下单首选 | `xttrader.order_stock(StockAccount, ...)` |
| 市价单参数 | `price_type=LATEST_PRICE`，`price=0` |

实测日志中的关键证据：

```text
QMT symbol get_trade_detail_data callable: globals=True builtins=False ContextInfo=False
QMT symbol passorder callable: globals=True builtins=False ContextInfo=False
QMT symbol cancel callable: globals=True builtins=False ContextInfo=False
QMT symbol order_stock callable: globals=False builtins=False ContextInfo=False
```

## 快照数据经验

1. 休盘时间不能用“资产字段为 0”直接判断账户为空。
2. `query_stock_positions(StockAccount)` 可能返回真实持仓，但 `query_stock_asset` 的 `total_asset`、`cash` 仍为 0。
3. 有些持仓对象会出现 `volume=0` 的伪记录，必须过滤，否则策略端会误判存在持仓。
4. 休盘时 `market_price` 可能为 0，但 `market_value` 有值，此时应按 `market_value / volume` 反推参考价。
5. 如果 `total_asset<=0` 但有持仓市值，快照层应兜底写 `available + market_value`，避免 Web 和策略端误判资产清零。

当前快照验证样例：

```json
{
  "account_id": "TEST_ACC_2",
  "source": "xttrader",
  "total_asset": 13356.0,
  "market_value": 13356.0,
  "positions": [
    {
      "stock": "600509.SH",
      "volume": 1800,
      "market_price": 7.42,
      "market_value": 13356.0
    }
  ]
}
```

## 代码开发避坑

1. **不要在 QMT 主循环里无节制写日志**  
   `handlebar()` 触发频率可能远高于预期。日志应按时间间隔输出摘要，例如 `tick ok accounts=2 ticks=...`。

2. **所有外部交易 API 都要有超时保护**  
   `connect()`、`subscribe()`、`query_*()` 都可能卡住。调用应放入短线程并 `join(timeout)`，超时后降级或跳过本轮。

3. **不要把 `LATEST_PRICE` 当成第 7 个参数**  
   `order_stock` 参数应是 `account, stock_code, order_type, order_volume, price_type, price, strategy_name, order_remark`。市价单应设置 `price_type=LATEST_PRICE`、`price=0`。

4. **下单、撤单、查询尽量传 `StockAccount`**  
   只读查询已验证 `StockAccount` 成功；字符串账号可保留为 fallback，但不应作为首选。

5. **大QMT脚本要保持 ASCII-only**  
   QMT 策略编辑器可能按 GBK 保存，非 ASCII 源码容易触发编码问题。脚本内部注释和字符串尽量英文，中文经验沉淀到 Markdown 文档。

6. **不要重发 `processing/` 残留订单**  
   executor 中断后，残留订单可能已经送柜台。恢复策略应写 `error` 回执并清理，不能移回 `pending/` 重发。

7. **策略端要先看心跳再下单**  
   大QMT离线时，`QmtIpcTrader` 应快速失败，不应等待完整 `QMT_IPC_ORDER_TIMEOUT`。

## 后续调试建议

1. 先做只读验证：心跳、两个账号 `account.json`、`source=xttrader`、持仓字段是否可信。
2. 再做低风险下单验证：优先选择不会成交的限价单，确认 `pending -> processing -> done` 与撤单链路。
3. 最后才做实盘有效价格验证，并保持单账号、单订单、最小数量。
