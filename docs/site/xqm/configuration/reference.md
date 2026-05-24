# 全量参数参考

## xtquant_manager_config.json 完整字段

```json
{
  "host": "127.0.0.1",
  "port": 8888,
  "api_token": "",
  "allowed_ips": [],
  "rate_limit": 60,
  "enable_hmac": false,
  "hmac_secret": "",
  "ssl_certfile": "",
  "ssl_keyfile": "",
  "health_check_interval": 30.0,
  "reconnect_cooldown": 60.0,
  "watchdog_interval": 10.0,
  "watchdog_restart_cooldown": 30.0,
  "heartbeat_interval": 1800.0,
  "enable_stop_profit": true,
  "stop_loss_ratio": -0.075,
  "initial_take_profit_ratio": 0.06,
  "initial_take_profit_pullback_ratio": 0.005,
  "initial_take_profit_sell_ratio": 0.6,
  "stop_profit_interval": 3.0,
  "stop_profit_dedup_seconds": 60.0,
  "accounts": [
    {
      "account_id": "必填",
      "qmt_path": "必填",
      "account_type": "STOCK",
      "call_timeout": 3.0,
      "connect_timeout": 30.0,
      "reconnect_base_wait": 60.0,
      "max_reconnect_attempts": 5,
      "ping_stock": "000001.SZ",
      "session_id": null
    }
  ]
}
```

## 服务级参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `host` | str | `"127.0.0.1"` | 监听地址，局域网访问改为实际 IP |
| `port` | int | `8888` | 监听端口 |
| `api_token` | str | `""` | API Token，空字符串表示不验证 |
| `allowed_ips` | list | `[]` | IP 白名单（支持 CIDR），空列表不限制 |
| `rate_limit` | int | `60` | 每分钟请求次数上限（按 IP 统计） |
| `enable_hmac` | bool | `false` | 启用 HMAC 请求签名验证 |
| `hmac_secret` | str | `""` | HMAC 密钥（`enable_hmac=true` 时必填） |
| `ssl_certfile` | str | `""` | TLS 证书路径，空字符串使用 HTTP |
| `ssl_keyfile` | str | `""` | TLS 私钥路径 |
| `health_check_interval` | float | `30.0` | HealthMonitor 轮询间隔（秒） |
| `reconnect_cooldown` | float | `60.0` | 重连最小冷却时间（秒） |
| `watchdog_interval` | float | `10.0` | 服务线程存活检查间隔（秒） |
| `watchdog_restart_cooldown` | float | `30.0` | 看门狗重启冷却（秒） |
| `heartbeat_interval` | float | `1800.0` | 心跳日志间隔（秒） |
| `enable_stop_profit` | bool | `true` | **启用止盈止损后台监控** |
| `stop_loss_ratio` | float | `-0.075` | 固定止损比例（成本价下跌 7.5% 触发） |
| `initial_take_profit_ratio` | float | `0.06` | 首次止盈触发阈值（盈利 6%） |
| `initial_take_profit_pullback_ratio` | float | `0.005` | 首次止盈回撤触发比例（0.5%） |
| `initial_take_profit_sell_ratio` | float | `0.6` | 首次止盈卖出比例（60%） |
| `stop_profit_interval` | float | `3.0` | 止盈止损检测间隔（秒） |
| `stop_profit_dedup_seconds` | float | `60.0` | 同信号去重窗口（秒） |

## AccountConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `account_id` | str | **必需** | QMT 交易账号 |
| `qmt_path` | str | **必需** | `userdata_mini` 目录路径（Windows 路径） |
| `account_type` | str | `"STOCK"` | `STOCK`（股票）/ `FUTURE`（期货） |
| `call_timeout` | float | `3.0` | 单次 API 调用超时（秒） |
| `connect_timeout` | float | `30.0` | xttrader 连接超时，超时后不挂起进程 |
| `reconnect_base_wait` | float | `60.0` | 指数退避起点（秒），每次翻倍直到 3600s |
| `max_reconnect_attempts` | int | `5` | 超过后停止退避，等待手动干预或 `on_disconnected` 重置 |
| `ping_stock` | str | `"000001.SZ"` | 健康探测用股票代码（ping 时查询此股票 tick） |
| `session_id` | int\|null | `null` | XtQuantTrader session id，null 时自动分配 |
