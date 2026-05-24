# 交易操作

所有交易接口均需 `X-API-Token` 认证（本机无 Token 时可省略）。

## 下单

```http
POST /api/v1/accounts/{account_id}/orders
Content-Type: application/json
X-API-Token: <token>
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `stock_code` | string | 是 | 股票代码，如 `000001.SZ` |
| `order_type` | int | 是 | `23` = 限价买入，`24` = 限价卖出 |
| `order_volume` | int | 是 | 股数（最小 100，100 的整数倍） |
| `price_type` | int | 否 | `11` = 限价（默认），`5` = 市价 |
| `price` | float | 否 | 限价单价格，市价单填 `0` |
| `strategy_name` | string | 否 | 策略标识，记录到交易备注 |
| `order_remark` | string | 否 | 订单备注 |

```json
{
  "stock_code": "000001.SZ",
  "order_type": 23,
  "order_volume": 100,
  "price_type": 11,
  "price": 10.50,
  "strategy_name": "grid",
  "order_remark": "网格第3层买入"
}
```

**响应（HTTP 201）：**

```json
{"success": true, "data": {"order_id": 2014314497}}
```

`order_id < 0` 表示下单失败（账号断线等）。

---

## 撤单

```http
DELETE /api/v1/accounts/{account_id}/orders/{order_id}
X-API-Token: <token>
```

**响应：**

```json
{"success": true, "data": {"result": 0, "order_id": 2014314497}}
```

`result = 0` 表示撤单请求已提交（不代表已成功撤销，需查询委托确认状态）。

---

## 查询持仓

```http
GET /api/v1/accounts/{account_id}/positions
X-API-Token: <token>
```

**响应：**

```json
{
  "success": true,
  "data": {
    "positions": [
      {
        "资金账号": "55009640",
        "证券代码": "300057",
        "股票余额": 7400,
        "可用余额": 0,
        "成本价": 6.661,
        "市值": 49358.0,
        "冻结数量": 7400
      }
    ]
  }
}
```

无持仓时 `positions` 为空数组。

---

## 查询资产

```http
GET /api/v1/accounts/{account_id}/asset
X-API-Token: <token>
```

**响应：**

```json
{
  "success": true,
  "data": {
    "资金账户": "55009640",
    "可用金额": 0.0,
    "冻结金额": 0.0,
    "持仓市值": 49358.0,
    "总资产": 544607.71
  }
}
```

---

## 查询当日委托

```http
GET /api/v1/accounts/{account_id}/orders
X-API-Token: <token>
```

返回当日所有委托列表（包含已成交、已撤销、未成交）。

---

## 查询当日成交

```http
GET /api/v1/accounts/{account_id}/trades
X-API-Token: <token>
```

返回当日所有成交记录。
