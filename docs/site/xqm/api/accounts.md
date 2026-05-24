# 账号管理

## 注册账号

```http
POST /api/v1/accounts
Content-Type: application/json
X-API-Token: <token>
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `account_id` | string | 是 | QMT 交易账号 |
| `qmt_path` | string | 是 | `userdata_mini` 路径 |
| `account_type` | string | 否 | `STOCK`（默认）/ `FUTURE` |
| `call_timeout` | float | 否 | 单次调用超时，默认 `3.0`s |
| `reconnect_interval` | float | 否 | 重连等待起点，默认 `60.0`s |
| `max_reconnect_attempts` | int | 否 | 最大退避次数，默认 `5` |

```json
{
  "account_id": "55009640",
  "qmt_path": "C:/QMT/userdata_mini",
  "account_type": "STOCK",
  "call_timeout": 3.0,
  "reconnect_interval": 60.0,
  "max_reconnect_attempts": 5
}
```

**响应（HTTP 201）：**

```json
{
  "success": true,
  "data": {
    "account_id": "55009640",
    "connected": true,
    "message": "注册成功"
  }
}
```

!!! note "幂等行为"
    账号已存在时重复注册同样返回 `201`，不报错。`connected` 反映当前连接状态。

---

## 注销账号

```http
DELETE /api/v1/accounts/{account_id}
X-API-Token: <token>
```

**响应（HTTP 200）：**

```json
{"success": true, "data": {"account_id": "55009640"}}
```

账号不存在时返回 `404`。

---

## 列出所有账号

```http
GET /api/v1/accounts
X-API-Token: <token>
```

**响应：**

```json
{
  "success": true,
  "data": {
    "accounts": ["55009640", "55009641"]
  }
}
```

---

## 账号状态

```http
GET /api/v1/accounts/{account_id}/status
X-API-Token: <token>
```

**响应：**

```json
{
  "success": true,
  "data": {
    "account_id": "55009640",
    "connected": true,
    "reconnecting": false,
    "reconnect_attempts": 0,
    "last_ping_ok_time": 1775550307.58,
    "connected_at": 1775550307.58,
    "xtdata_available": true,
    "xttrader_available": true
  }
}
```

| 字段 | 说明 |
|------|------|
| `connected` | 是否已连接 |
| `reconnecting` | 是否正在重连中 |
| `reconnect_attempts` | 当前累计重连次数 |
| `last_ping_ok_time` | 上次 ping 成功的 Unix 时间戳 |
| `xtdata_available` | xtdata 行情接口是否可用 |
| `xttrader_available` | xttrader 交易接口是否可用 |
