# 行情接口

## 实时 Tick

```http
GET /api/v1/market/tick?stock_codes=000001.SZ,600036.SH&account_id=55009640
X-API-Token: <token>
```

**查询参数：**

| 参数 | 说明 |
|------|------|
| `stock_codes` | 逗号分隔的股票代码，如 `000001.SZ,600036.SH` |
| `account_id` | 使用哪个账号的 xtdata 连接获取数据 |

**响应：**

```json
{
  "success": true,
  "data": {
    "000001.SZ": {
      "lastPrice": 10.52,
      "open": 10.40,
      "high": 10.60,
      "low": 10.35,
      "volume": 123456789,
      "amount": 1298765432.0,
      "bidPrice": [10.51, 10.50, 10.49, 10.48, 10.47],
      "askPrice": [10.52, 10.53, 10.54, 10.55, 10.56]
    }
  }
}
```

---

## 历史行情

```http
GET /api/v1/market/history
  ?stock_code=000001.SZ
  &account_id=55009640
  &period=1d
  &start_time=20260101
  &end_time=20260411
X-API-Token: <token>
```

**查询参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `stock_code` | — | 单只股票代码 |
| `account_id` | — | 账号 ID |
| `period` | `1d` | K 线周期：`1m` `5m` `15m` `30m` `60m` `1d` |
| `start_time` | `20200101` | 开始日期，格式 `YYYYMMDD` |
| `end_time` | `""` | 结束日期，空表示今天 |

**响应：**

```json
{
  "success": true,
  "data": {
    "000001.SZ": [
      {
        "time": 20260101093000000,
        "open": 10.20,
        "high": 10.60,
        "low": 10.15,
        "close": 10.52,
        "volume": 123456789,
        "amount": 1298765432.0
      }
    ]
  }
}
```

---

## 下载历史数据

将历史数据下载到本地 QMT 数据库，下载后可使用历史行情接口查询。

```http
POST /api/v1/market/download
Content-Type: application/json
X-API-Token: <token>
```

```json
{
  "account_id": "55009640",
  "stock_code": "000001.SZ",
  "period": "1d",
  "start_time": "20260101",
  "end_time": "20260411"
}
```

**响应：**

```json
{"success": true, "data": null}
```

!!! note "异步操作"
    下载为后台任务，接口返回时下载可能尚未完成。大批量数据下载可能需要数分钟。
