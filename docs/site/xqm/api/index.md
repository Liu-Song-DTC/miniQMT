# API 概述

**Base URL**: `http://{host}:{port}/api/v1`

## 认证

请求头 `X-API-Token: <token>`。本机访问（`127.0.0.1`）或未配置 `api_token` 时可省略。

```http
GET /api/v1/accounts
X-API-Token: your-secret-token
```

`/api/v1/health` 和 `/api/v1/health/{account_id}` **始终无需认证**，供存活探针使用。

## 统一响应格式

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

失败时 `success=false`，`error` 字段包含错误信息：

```json
{
  "success": false,
  "data": null,
  "error": "账号不存在: 55009640"
}
```

## HTTP 状态码

| 状态码 | 含义 |
|-------|------|
| `200` | 成功 |
| `201` | 创建成功（注册账号、下单） |
| `401` | Token 错误或缺失 |
| `403` | IP 未在白名单 |
| `404` | 账号不存在 |
| `422` | 请求参数格式错误 |
| `429` | 超过速率限制 |
| `502` | xtquant 调用失败 |
| `504` | 操作超时（超过 `call_timeout`） |

## 接口分组

| 分组 | 端点前缀 | 说明 |
|------|---------|------|
| [账号管理](accounts.md) | `/api/v1/accounts` | 注册、注销、列表、状态 |
| [交易操作](trading.md) | `/api/v1/accounts/{id}/orders` | 下单、撤单、持仓、资产、委托、成交 |
| [行情接口](market.md) | `/api/v1/market` | 实时 Tick、历史行情、下载数据 |
| [可观测性](observability.md) | `/api/v1/health` `/api/v1/metrics` | 健康检查、调用指标 |
| **止盈止损** | `/api/v1/stop-profit` | **状态查询、配置更新、启停切换** |
