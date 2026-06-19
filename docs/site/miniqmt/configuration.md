# 配置参考

所有可配置参数集中在 `config.py` 中。**严禁在业务代码中硬编码魔法数字。**

---

## 核心功能开关

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_SIMULATION_MODE` | `True` | `True` = 模拟，`False` = 实盘 |
| `ENABLE_AUTO_TRADING` | `False` | 自动交易执行开关 |
| `ENABLE_DYNAMIC_STOP_PROFIT` | `True` | 动态止盈止损功能 |
| `ENABLE_GRID_TRADING` | `True` | 网格交易功能 |
| `ENABLE_ALLOW_BUY` | `True` | 允许买入 |
| `ENABLE_ALLOW_SELL` | `True` | 允许卖出 |
| `DEBUG` | `False` | 调试模式 |
| `DEBUG_SIMU_STOCK_DATA` | `False` | 模拟股票数据（绕过交易时间限制） |

!!! danger "实盘交易前必须检查"
    1. `ENABLE_SIMULATION_MODE = False`
    2. `ENABLE_AUTO_TRADING = True`
    3. QMT 客户端已启动并登录
    4. `account_config.json` 配置正确

---

## 交易参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `POSITION_UNIT` | `35000` | 单次买入金额（元） |
| `MAX_POSITION_VALUE` | `70000` | 单只股票最大持仓市值（元） |
| `MAX_TOTAL_POSITION_RATIO` | `0.95` | 总持仓占比上限（95%） |
| `SIMULATION_BALANCE` | `1000000` | 模拟模式初始资金（元） |

---

## 止盈止损参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `STOP_LOSS_RATIO` | `-0.075` | 止损比例：成本价下跌 7.5% |
| `INITIAL_TAKE_PROFIT_RATIO` | `0.06` | 首次止盈触发：盈利 6% |
| `INITIAL_TAKE_PROFIT_PULLBACK_RATIO` | `0.005` | 首次止盈回撤触发：从高点回落 0.5% |
| `INITIAL_TAKE_PROFIT_RATIO_PERCENTAGE` | `0.6` | 首次止盈卖出比例：60% |

### 动态止盈档位

```python
DYNAMIC_TAKE_PROFIT = [
    (0.05, 0.96),   # 最高浮盈 5% 时，止盈位 = 最高价 × 96%
    (0.10, 0.93),   # 最高浮盈 10% 时，止盈位 = 最高价 × 93%
    (0.15, 0.90),
    (0.20, 0.87),
    (0.30, 0.85),   # 最高浮盈 30% 时，止盈位 = 最高价 × 85%
]
```

---

## 网格交易参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `GRID_CALLBACK_RATIO` | `0.005` | 回调触发比例（0.5%） |
| `GRID_LEVEL_COOLDOWN` | `60` | 同一档位冷却时间（秒） |
| `GRID_BUY_COOLDOWN` | `300` | 买入成功后冷却（秒） |
| `GRID_SELL_COOLDOWN` | `300` | 卖出成功后冷却（秒） |
| `GRID_REQUIRE_PROFIT_TRIGGERED` | `True` | 网格启动前需先触发止盈 |
| `GRID_MAX_DEVIATION_RATIO` | `0.15` | 最大偏离中心价比例（±15%） |
| `GRID_TARGET_PROFIT_RATIO` | `0.10` | 网格目标盈利比例（10%） |
| `GRID_STOP_LOSS_RATIO` | `-0.10` | 网格止损比例（-10%） |

### 网格实盘交易参数（仅 `ENABLE_SIMULATION_MODE = False` 生效）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `GRID_CONFIRM_LIVE_ORDER_BY_DEAL` | `True` | 实盘下单后以**成交回报**为准更新统计（推荐保持开启） |
| `GRID_SIGNAL_MAX_AGE_SECONDS` | `60` | 网格信号最长有效期（秒），超龄丢弃 |
| `GRID_SIGNAL_MAX_PRICE_DRIFT_RATIO` | `0.01` | 执行前最新价相对触发价最大容忍偏离（1%） |
| `GRID_USE_COUNTERPARTY_PRICE` | `True` | 实盘用对手价下单（买取卖三价/卖取买三价）提高成交概率 |
| `GRID_COUNTERPARTY_BUY_PRICE_BUFFER_RATIO` | `0.02` | 对手价买入资金预占缓冲（2%），防止超 `max_investment` |
| `GRID_ENABLE_PRICE_LIMIT_GUARD` | `True` | 下单前检查涨跌停/停牌，封板跳过本次交易 |
| `GRID_PRICE_LIMIT_EPS` | `0.001` | 涨跌停判定容差（元），补偿浮点误差 |

!!! info "对手价依赖成交确认"
    `GRID_USE_COUNTERPARTY_PRICE` 仅在 `GRID_CONFIRM_LIVE_ORDER_BY_DEAL = True` 时启用——成交以真实回报价落账，统计才准确。详见[网格交易 · 实盘交易机制](grid-trading.md)。

---

## 线程与监控参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_THREAD_MONITOR` | `True` | 线程自愈监控 |
| `THREAD_CHECK_INTERVAL` | `60` | 线程检查间隔（秒） |
| `THREAD_RESTART_COOLDOWN` | `60` | 重启冷却时间（秒） |
| `MONITOR_LOOP_INTERVAL` | `3` | 持仓监控循环间隔（秒） |
| `MONITOR_CALL_TIMEOUT` | `8.0` | 持仓监控 API 调用超时（秒） |
| `MONITOR_NON_TRADE_SLEEP` | `60` | 非交易时段休眠（秒） |
| `GRID_POSITION_QUERY_TIMEOUT` | `5.0` | 网格交易持仓查询超时（秒） |
| `HISTORY_DATA_DOWNLOAD_TIMEOUT` | `5` | 启动时单只股票历史数据下载超时（秒），超时跳过 |
| `GRID_LOCK_ACQUIRE_TIMEOUT` | `5.0` | 网格交易锁获取超时（秒） |
| `QMT_POSITION_QUERY_INTERVAL` | `10.0` | QMT 持仓查询间隔（秒） |
| `POSITION_SYNC_INTERVAL` | `15.0` | SQLite 同步间隔（秒） |
| `CLEARED_POSITION_WARNING_INTERVAL` | `1800` | 清仓残留持仓成本价告警限频（秒），`0` 不限频；券商盘后可能仍返回已清仓行，超频降为 DEBUG |
| `ENABLE_SELL_MONITOR` | `True` | 卖出委托超时监控 |
| `ENABLE_HEARTBEAT_LOG` | `True` | 心跳日志 |
| `HEARTBEAT_INTERVAL` | `1800` | 心跳间隔（30 分钟） |

---

## Web 服务参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `WEB_SERVER_HOST` | `"127.0.0.1"` | web1.0 Flask 监听地址，默认仅本机访问 |
| `WEB_SERVER_PORT` | `5000` | 监听端口 |
| `WEB_API_TOKEN` | `""` | API Token（通过 `QMT_API_TOKEN` 环境变量设置） |

---

## 行情与历史数据参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_PERIOD` | `"1d"` | 默认行情周期 |
| `INITIAL_DAYS` | `365` | 初始拉取历史天数 |
| `UPDATE_INTERVAL` | `60` | 行情更新间隔（秒） |
| `HISTORY_UPDATE_THROTTLE_SECONDS` | `300` | 单只股票历史数据更新节流，避免策略线程每轮重复拉日线 |
| `HISTORY_INVALID_DATE_LOG_INTERVAL` | `600` | 同一股票同一数据源非法历史日期告警降噪间隔 |

历史数据源策略为 `xtdata` 优先、`Mootdx` 兜底；历史日期会做格式规范化和范围过滤，异常或空数据会降级跳过而不阻塞主循环。

---

## 自动买入配置

自动买入模块使用独立配置文件 `autobuy/miniqmt_autobuy.cfg`，不放在 `config.py` 中。与主程序相关联的配置主要有：

| 参数 | 位置 | 说明 |
|------|------|------|
| `POSITION_UNIT` | `config.py` | 自动买入最终复用 Web 买入 API，单笔金额沿用主程序买入金额 |
| `QMT_API_TOKEN` | 环境变量 | 若 Flask Web 开启 Token，需同步写入 `[web].api_token` |
| `[web].base_url` | `autobuy/miniqmt_autobuy.cfg` | 目标账号 Web 服务地址，多账号时按端口切换 |
| `[risk].max_buys_per_run` | `autobuy/miniqmt_autobuy.cfg` | 单次触发最多买入数量 |
| `[schedule].only_trade_time` | `autobuy/miniqmt_autobuy.cfg` | 使用真实市场时段判断，区别于模拟模式下恒为 True 的 `is_trade_time()` |

完整说明见[自动买入模块](autobuy.md)。

---

## 日志参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `"INFO"` | 日志级别 |
| `LOG_FILE` | `"qmt_trading.log"` | 日志文件路径 |
| `LOG_MAX_SIZE` | `10 MB` | 单个日志文件最大大小 |
| `LOG_BACKUP_COUNT` | `5` | 日志备份数量 |

---

## 配置文件格式

### account_config.json

```json
{
  "account_id": "您的交易账号",
  "account_type": "STOCK",
  "qmt_path": "C:/光大证券金阳光QMT实盘/userdata_mini"
}
```

### stock_pool.json

```json
["000001.SZ", "600036.SH", "000333.SZ"]
```
