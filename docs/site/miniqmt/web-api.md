# Web API

miniQMT 提供 RESTful API。**两种后端**都暴露下列端点（端点路径相同）：

| 后端 | 默认地址 | 适用 |
|------|---------|-----|
| Flask 直连 (`web_server.py`) | `http://127.0.0.1:5000`（每账号一个端口） | web1.0、单机完整功能 |
| xtquant_manager 网关 | `http://127.0.0.1:8888` | web2.0、多账号、远程访问 |

**认证**：需要 Token 的接口通过 `QMT_API_TOKEN` 环境变量（Flask）或 `api_token` 配置（网关）设置。

**多账号路由（网关）**：通过 `X-Account-Id` 请求头切换目标账号；未指定时回退到第一个已注册账号。

下列表格中 **🌐 网关** 列含义：

- ✅ 完整 — 网关模式可用，行为与 Flask 一致
- 🔒 只读 — 网关模式仅返回数据，不接受写操作
- ❌ 不可用 — 网关未实现，需 Flask 直连模式

---

## 系统状态

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| GET | `/api/connection/status` | QMT 连接状态 | ✅ 完整 |
| GET | `/api/status` | 系统运行状态总览 | ✅ 完整 |
| GET | `/api/debug/status` | 详细调试状态 | ❌ |
| GET | `/api/accounts` | 列出已注册账号（无 Token，供前端账号发现） | ✅ 完整 |

---

## 持仓与交易记录

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| GET | `/api/positions` | 当前持仓列表（含 SQLite 持久化字段：名称/建仓日/止损价） | ✅ 完整 |
| GET | `/api/positions-all` | 全部持仓详情 | ✅ 完整 |
| GET | `/api/trade-records` | 交易记录（优先读 SQLite `trade_records`） | ✅ 完整 |
| POST | `/api/initialize_positions` | 初始化持仓数据 | ❌ |
| POST | `/api/holdings/init` | 初始化持股配置 | ❌ |

---

## 交易操作

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| POST | `/api/actions/execute_buy` | 执行买入 | ✅ 完整 |
| POST | `/api/actions/execute_sell` | 执行卖出 | ✅ 完整 |
| POST | `/api/actions/execute_trading_signal` | 执行指定交易信号 | ❌ |

**买入参数**：

```json
{
  "stock_code": "000001.SZ",
  "amount": 100,
  "strategy": "manual"
}
```

---

## 网格交易 API

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| POST | `/api/grid/start` | 启动网格会话 | ❌ |
| POST | `/api/grid/stop/<session_id>` | 停止指定网格 | ❌ |
| POST | `/api/grid/stop` | 停止所有网格 | ❌ |
| GET | `/api/grid/session/<stock_code>` | 按股票查网格状态 | ❌ |
| GET | `/api/grid/session/<session_id>` | 按会话 ID 查详情 | ❌ |
| GET | `/api/grid/sessions` | 所有网格会话 | ❌ |
| GET | `/api/grid/trades/<session_id>` | 网格交易记录 | ❌ |
| GET | `/api/grid/status/<stock_code>` | 网格快速状态 | ❌ |
| GET | `/api/grid/config` | 网格配置 | ❌ |
| GET | `/api/grid/templates` | 网格模板列表 | ❌ |
| POST | `/api/grid/template/save` | 保存网格模板 | ❌ |
| DELETE | `/api/grid/template/<name>` | 删除模板 | ❌ |
| POST | `/api/grid/template/use` | 使用模板 | ❌ |
| GET | `/api/grid/template/default` | 获取默认模板 | ❌ |
| PUT | `/api/grid/template/<name>/default` | 设为默认模板 | ❌ |
| GET | `/api/grid/risk-templates` | 风险分级模板 | ❌ |

!!! info "网格交易仅 Flask 直连"
    网格策略由 `grid_trading_manager` 主线程驱动，网关进程独立运行不持有策略状态，因此整组网格 API 仅 Flask 模式可用。

!!! tip "统一盈亏快照"
    `/api/grid/session/<...>`、`/api/grid/sessions`、`/api/grid/status/<stock_code>` 返回的会话数据含 `pnl_snapshot` 字段：基于 FIFO 账本计算的真实盈亏（`realized_pnl` / `unrealized_pnl` / `total_pnl` / `profit_ratio`），账本不可用时自动降级并以 `is_degraded` 标记。详见[网格交易 · 真实盈亏账本](grid-trading.md)。

---

## 配置管理

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| GET | `/api/config` | 获取系统配置 | 🔒 只读（返回默认值） |
| POST | `/api/config/save` | 保存配置（需 Token） | ❌ |

---

## 监控控制

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| POST | `/api/monitor/start` | 启动持仓监控 | ❌ |
| POST | `/api/monitor/stop` | 停止持仓监控 | ❌ |

---

## 股票池

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| GET | `/api/stock_pool/list` | 获取股票池列表 | ❌ |

---

## 实时推送

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| GET | `/api/sse` | Server-Sent Events 实时更新 | ❌（用 3s/10s 轮询） |
| GET | `/api/positions/stream` | 持仓数据流 | ❌ |

---

## 数据管理（需 Token）

| 方法 | 路径 | 说明 | 🌐 网关 |
|------|------|------|--------|
| POST | `/api/logs/clear` | 清空日志 | ❌ |
| POST | `/api/data/clear_buysell` | 清除买卖数据 | ❌ |
| POST | `/api/data/import` | 导入数据 | ❌ |

---

## XtQuantManager 专属 API（v1）

网关模式额外提供 [`/api/v1/*`](../xqm/api/index.md) 端点（多账号管理、健康检查、动态止盈、Prometheus metrics 等）。详见 [XtQuantManager API 手册](../xqm/api/index.md)。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 网关全局健康（账号总数 / 在线数） |
| GET | `/api/v1/accounts` | 账号列表（需 Token） |
| GET | `/api/v1/stop-profit/status` | 动态止盈运行状态 |
| GET | `/api/v1/stop-profit/config` | 止盈配置 |
| POST | `/api/v1/stop-profit/toggle` | 启用/禁用动态止盈 |
