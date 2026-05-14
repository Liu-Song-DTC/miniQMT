# Changelog

本文件记录 miniQMT 项目所有重要变更，格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [SemVer 2.0.0](https://semver.org/lang/zh-CN/)。

> 本文件是 **唯一的变更记录源**。文档站 `/changelog/` 页面通过 `include-markdown` 引用本文件，请在此处直接编辑。

## [Unreleased]

### Added
- 统一文档体系：MkDocs + mkdocstrings（docstring 自动抽取）+ include-markdown（CHANGELOG 引用）+ 本地热重载 `start_docs.bat`
- 文档构建依赖独立到 `utils/requirements-docs.txt`，不污染运行环境
- GitHub Actions 部署工作流加 `if: false` 守门，未来开启只需删除一行

### Changed
- `docs/site/` 作为唯一 markdown 源，根目录 `CHANGELOG.md` 作为变更日志唯一真源

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

[Unreleased]: https://github.com/weihong-su/miniQMT/compare/V2.0.0-Beta...HEAD
[2.0.0-Beta]: https://github.com/weihong-su/miniQMT/compare/V1.0.0...V2.0.0-Beta
[1.0.0]: https://github.com/weihong-su/miniQMT/releases/tag/V1.0.0
