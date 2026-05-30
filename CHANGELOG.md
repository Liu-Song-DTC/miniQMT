# Changelog

本文件记录 miniQMT 项目所有重要变更，格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [SemVer 2.0.0](https://semver.org/lang/zh-CN/)。

> 本文件是 **唯一的变更记录源**。文档站 `/changelog/` 页面通过 `include-markdown` 引用本文件，请在此处直接编辑。

## [Unreleased]

## [3.1.0] - 2026-05-30

### Added
- **web2.0 启动模式选择**: `miniqmt.bat` 菜单 [7]/[8]/[9] 启动前可选 `web1.0` (Flask :5000 起) 或 `web2.0` (xtquant_manager :8888)，偏好持久化到 `data/.web_mode`
- **xtquant_manager 内嵌 web2.0**: 网关启动后 `http://localhost:8888/` 直接托管 `web2.0/dist/`（静态文件 + SPA fallback），菜单 [g] 打开浏览器
- **Flask 兼容 API 端点**（`xtquant_manager/server.py`）使 web2.0 前端无需改造即可在网关模式下运行：
  - `GET /api/status` `/api/positions` `/api/positions-all` `/api/connection/status` `/api/config` `/api/trade-records`
  - `GET /api/accounts` — 无 Token 公开列出账号 ID，互联网只读用户也能正确发现多账号（无 token 时不再退化为只显示第一个账号）
  - 字段映射对齐 Flask 顶层格式，QMT 实时数据 + SQLite 持久化元数据合并，账号隔离基于 `X-Account-Id` 请求头
- **网关模式动态止盈状态查询**: `/api/v1/stop-profit/status` `/config` `/toggle`，复用 `position_manager` 算法
- **网关模式只读防护**: web2.0 在 `isGatewayMode()` 时禁用监控开关/动态止盈控制/参数保存/模拟买入/初始化按钮，显示「🔒 网关模式 · 只读监控+下单」徽章
- **连接设置面板**: 顶部齿轮 ⚙ 进入，支持「网关模式 / 直连模式」切换、网关地址 + API Token 配置、测试连接（8s 超时 + 非 JSON 检测 + 详细错误）、HTTPS Mixed Content 警告、保存后自动 `discoverAccounts()` 刷新账号下拉
- **iPhone / 移动端适配**: 持仓表格 `overflow-x-auto` 横向滚动 + `min-w-[800px]` 保表头不挤压；HeaderBar 按 `sm:` 断点响应式堆叠；竖向单列布局 + 止盈列改图标
- **Vercel 一键远程部署**: 根目录新增 `vercel.json` 指定 web2.0 构建命令与输出目录，配合 Cloudflare Tunnel 实现「Vercel 前端 + Windows QMT 后端」远程部署
- **绑定地址与客户端地址分离**：`XQM_DEFAULT_HOST=0.0.0.0` (绑定) + `XQM_CLIENT_HOST=127.0.0.1` (客户端目标)；启动菜单同时显示「本机 URL」+「局域网 URL」方便从其他设备访问

### Changed
- **web2.0 交易日志**: 网关模式从「QMT 当日成交/委托」改为优先读 SQLite `trade_records` 表（与 web1.0 同源，含名称/时间/策略/历史买卖），SQLite 无记录时回退 QMT
- **web2.0 持仓字段补齐**: 改用 SQLite 持久化数据替代 xtdata/公式估算，网关模式下持仓名称、建仓日期、止损价能正确显示
- **web2.0 盈亏颜色按 A 股习惯**: 红涨绿跌（与原默认的绿涨红跌相反）
- **web2.0 监控/止盈按钮文案**: 「开始监控/停止监控」「开启动态止盈/禁用动态止盈」（替代 ON/OFF）
- **web2.0 配置面板布局**: 4 列网格 + 标签右对齐 + 紧凑输入框；买入操作整合到 HeaderBar 第 3 行（移除独立 BuyPanel 卡片）
- **web1.0 默认只绑本机**: `WEB_SERVER_HOST=127.0.0.1`，web2.0/xtquant_manager 负责对外（避免 web1.0 误暴露完整写操作 API 到公网）
- **`xtquant_manager` 健康检查日志降噪**: 减少非异常情况下的常规健康检查输出

### Fixed
- **web2.0 网关模式涨跌幅恒为 0**: 持仓裸代码缺少市场后缀（`.SZ`/`.SH`），网关请求 tick 失败，补齐后缀
- **web1.0 持仓不刷新**: SSE `onmessage` 因 `wasSimulationMode` 未定义崩溃，导致后续推送被中断
- **web2.0 连接设置变更后账号下拉未刷新**: 切换网关 URL/Token 后自动调用 `discoverAccounts()` 同步真实账号列表
- **web2.0 互联网用户只能看到第一个账号**: 无 Token 时无法访问 `/api/v1/accounts`，新增公开 `/api/accounts` Flask 兼容端点
- **web2.0 盈亏比例显示错误**: `fmtPercent` 多乘 100（小数→百分比转换），与 web1.0 对齐
- **web2.0 持仓价格精度**: 统一 2 位小数（原 3 位），与 A 股报价精度一致
- **launcher 0.0.0.0 不能作客户端目标**: 健康检查、菜单 UI 打开统一改用 `127.0.0.1`

### Docs
- 新增「Web 前端（web1.0 / web2.0）」章节：双模式架构、网关能力边界、连接设置、启动菜单、Vercel 远程部署 — 见文档站
- `web-api.md` 标注哪些端点在 xtquant_manager 网关模式下可用
- `CLAUDE.md` 同步 Web 双模式架构说明（commit 7035354d）

## [3.0.0] - 2026-05-24

### Added
- **XtQuantManager 动态止盈止损**: 网关模式下独立运行的止盈止损后台监控 (`xtquant_manager/stop_profit.py`)
  - 直接复用 `position_manager.py` 中已验证的止损/首次止盈/动态止盈算法
  - 信号去重（60s 窗口）+ 自动下单（实盘 xttrader 接口）
  - API 端点：`/api/v1/stop-profit/status`、`/config`、`/toggle`
- **web2.0 Vue3 前端**: 全新的持仓管理 Web 界面 (`web2.0/`)
  - Vue3 + Vite + TypeScript + Tailwind CSS + Pinia 状态管理
  - PWA 支持 (vite-plugin-pwa)，可安装到桌面离线使用
  - 双后端兼容：Flask (web1.0 API) + xtquant_manager (v1 API)
  - 多账户切换、连接设置面板、SSE 实时推送 + 智能轮询
  - 止盈止损开关（与 web1.0 `firstProfitSellEnabled` 对齐）
  - Vercel 一键部署支持 (见 `web2.0/VERCEL_DEPLOY.md`)
- **miniqmt.bat 新增 XtQuantManager 菜单**: [d] 启动 [e] 停止 [f] 状态 [g] UI [h] 重启 [i] 日志
- 统一文档体系：MkDocs + mkdocstrings（docstring 自动抽取）+ include-markdown（CHANGELOG 引用）+ 本地热重载 `start_docs.bat`
- 文档构建依赖独立到 `utils/requirements-docs.txt`，不污染运行环境
- GitHub Actions 部署工作流加 `if: false` 守门，未来开启只需删除一行

### Changed
- `docs/site/` 作为唯一 markdown 源，根目录 `CHANGELOG.md` 作为变更日志唯一真源
- web2.0 配置百分比字段统一精度到 2 位小数，金额字段整数显示
- 界面全面视觉升级：渐变背景、毛玻璃顶栏、分层阴影卡片、动画模态框、盈亏色条

### Security
- **隐私安全加固**: `Methods.py` 硬编码 Pushplus Token 改为 `PUSHPLUS_TOKEN` 环境变量
- `web2.0/src/api/accounts.ts` 默认账户去真实 ID，改为空占位符
- `.gitignore` 新增 `web2.0/dist/` 和 `web2.0/node_modules/`
- 文档示例中的真实账号 ID 替换为 `55009640` 等虚构 ID

---

## [2.0.0-Beta] - 2026-03-28

### Added
- 完整回归测试框架：23 组 × 67 模块 × 1170 个测试用例，全部通过（100%）
- 网格交易全区间覆盖测试（114 个用例，A–K 11 个套件）
- XtQuantManager HTTP 网关：多账号注册 + 健康检查 + Fail-Safe 重连
- 非 XtQuantManager 场景的 QMT 重连机制（事件 / 循环 / 主动探测三条路径）
- 盘前 9:25 自动重新初始化 xtquant 接口

### Fixed
- baostock 登录无超时保护导致监控线程阻塞约 168 秒
- 止盈触发标志写入后 positions_cache 未失效导致 10 秒窗口内重复信号
- `qmt_connected` 初始化后永不更新（永久假健康）
- `easy_qmt_trader` 缺少 `reconnect_xttrader()` 方法
- 线程监控未注册 `heartbeat_check`，无法感知 API 断连

### Changed
- 线程注册统一使用 `lambda` 获取最新对象引用，避免重启后引用失效

---

## [1.0.0] - 2026-02-03

### Added
- 首个稳定版本
- 双层存储架构（内存数据库 + SQLite 持久化）
- 信号检测与执行分离设计
- 动态止盈止损策略（最高浮盈 5%/10%/15%/20%/30% 五档）
- 网格交易完整实现
- Web 前端实时监控界面（Flask + SSE）
- 多线程协同 + 线程自愈机制
- 模拟交易模式（无需 QMT 即可验证策略）
- 回归测试框架基础设施

[Unreleased]: https://github.com/weihong-su/miniQMT/compare/v3.1.0...HEAD
[3.1.0]: https://github.com/weihong-su/miniQMT/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/weihong-su/miniQMT/compare/V2.0.0-Beta...v3.0.0
[2.0.0-Beta]: https://github.com/weihong-su/miniQMT/compare/V1.0.0...V2.0.0-Beta
[1.0.0]: https://github.com/weihong-su/miniQMT/releases/tag/V1.0.0
