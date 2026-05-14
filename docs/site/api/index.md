# API 参考

本页 API 文档由 [mkdocstrings](https://mkdocstrings.github.io/python/) 从源码 docstring **自动抽取**，无需手工同步。修改源码 docstring 后，`mkdocs serve` 会自动热重载页面。

## 约定

- **docstring 风格**：[Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- **类型注解**：函数签名展示 Python type hints（`mkdocs.yml` 中 `show_signature_annotations: true`）
- **私有成员**：默认不展示（下划线开头方法），如需暴露请在源码中显式添加 `__all__`

## 模块索引

### 网格交易

- [grid_trading_manager](grid-trading-manager.md) — 网格交易会话管理与信号检测
- [grid_database](grid-database.md) — 网格交易 SQLite 持久化
- [grid_validation](grid-validation.md) — 网格参数 Marshmallow 校验

### 持仓与执行

- [position_manager](position-manager.md) — 持仓管理核心（内存 + SQLite 双层）

### XtQuantManager

- [account](xqm-account.md) — `XtQuantAccount` 单账号封装
- [manager](xqm-manager.md) — `XtQuantManager` 多账号注册表
- [health_monitor](xqm-health.md) — 后台健康检查线程
- [server](xqm-server.md) — FastAPI HTTP 网关

## 扩展抽取范围

向 [`mkdocs.yml`](https://github.com/weihong-su/miniQMT/blob/main/mkdocs.yml) `nav` 段添加新页面，在该页面写：

```markdown
# 模块名
::: 模块导入路径
```

mkdocstrings 会自动渲染该模块的所有公开 class / function。
