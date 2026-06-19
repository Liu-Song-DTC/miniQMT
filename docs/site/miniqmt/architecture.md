# 架构说明

## 核心设计原则

### 信号检测与执行分离（最重要）

```
持仓监控线程（始终运行） → 检测信号 → latest_signals 队列
                                      ↓
策略执行线程 → 检查 ENABLE_AUTO_TRADING → 执行 / 忽略信号
```

- 监控线程**始终运行**，持续检测信号（即使 `ENABLE_AUTO_TRADING=False`）
- `ENABLE_AUTO_TRADING` 只控制**是否执行**检测到的信号
- 每个信号经过 `validate_trading_signal()` 验证，防止重复执行

### 双层存储架构

```
实盘模式:
  QMT 实盘账户 → qmt_trader.position() → 内存数据库
  内存数据库 → 定时同步（15 秒） → SQLite 数据库

模拟模式:
  Web 界面 → trading_executor → simulate_buy/sell() → 内存数据库
```

- **内存数据库**：高频更新数据（价格、市值、盈亏比例）
- **SQLite**：持久化关键状态（开仓日期、止盈标记、最高价）
- 修改内存数据后必须调用 `_increment_data_version()` 触发前端更新

---

## 线程架构

| 线程 | 职责 | 频率 | 关键配置 |
|------|------|------|---------|
| 线程监控 | 检测线程崩溃并自动重启 | 60 秒 | `THREAD_CHECK_INTERVAL` |
| 数据更新 | 更新股票池行情数据 | 60 秒 | — |
| 持仓监控 | 同步实盘持仓、更新价格、检测信号 | 3 秒 | `MONITOR_LOOP_INTERVAL` |
| 策略执行 | 获取信号、执行交易 | 5 秒 | `ENABLE_AUTO_TRADING` |
| 网格交易 | 网格信号检测与买卖执行 | 5 秒 | `ENABLE_GRID_TRADING` |
| 卖出监控 | 委托单超时撤单 | 2 秒 | `ENABLE_SELL_MONITOR` |
| 定时同步 | 内存 → SQLite 同步 | 15 秒 | `POSITION_SYNC_INTERVAL` |
| Web 服务 | RESTful API | 持续 | — |
| 心跳日志 | 定期输出系统运行状态 | 30 分钟 | `ENABLE_HEARTBEAT_LOG` |
| 盘前同步 | 重新初始化 xtquant | 每日 9:25 | `ENABLE_PREMARKET_XTQUANT_REINIT` |
| 自动买入 | 候选池筛选与 Web API 买入 | 独立进程定时触发 | `autobuy/miniqmt_autobuy.cfg` |

---

## 模块职责

```
config.py              # 集中配置管理
logger.py              # 统一日志管理
main.py                # 系统启动入口和线程管理
thread_monitor.py      # 线程健康监控与自愈
data_manager.py        # 历史数据获取（xtdata 接口）
indicator_calculator.py # 技术指标计算
position_manager.py    # 持仓管理核心（内存 + SQLite 双层）
trading_executor.py    # 交易执行器（xttrader 接口）
strategy.py            # 交易策略逻辑
web_server.py          # RESTful API 服务（Flask）
easy_qmt_trader.py     # QMT 交易 API 封装
premarket_sync.py      # 盘前同步与初始化
config_manager.py      # 配置持久化管理
sell_monitor.py        # 卖出委托单超时监控与撤单
grid_trading_manager.py # 网格交易会话管理
grid_database.py       # 网格交易数据持久化（SQLite）
grid_validation.py     # 网格交易参数校验
autobuy/               # 自动买入独立进程：候选池筛选、防重、HTTP 下单
xtquant_manager/       # XtQuantManager HTTP 网关（可选）
```

---

## 优雅关闭流程

系统退出时按以下顺序关闭（`main.py` 的 `cleanup()` 函数）：

```
1. Web 服务器 → 停止接收新请求
2. 线程监控器 → 停止监控循环
3. 业务线程 → 停止数据更新、持仓监控、策略执行
4. 核心模块 → 按依赖顺序关闭
```

每个步骤都有独立的异常处理，确保单个步骤失败不影响其他资源清理。
