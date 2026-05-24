# 单账号（开发/测试）

最简配置，无需认证，适合本机开发调试。

## 配置文件

将以下内容保存为项目根目录的 `xtquant_manager_config.json`：

```json
{
  "host": "127.0.0.1",
  "port": 8888,
  "api_token": "",
  "accounts": [
    {
      "account_id": "55009640",
      "qmt_path": "C:/QMT/userdata_mini",
      "account_type": "STOCK"
    }
  ]
}
```

## 启动方式

=== "管理脚本（推荐）"

    ```bat
    xtquant_manager\xqm_manager.bat start
    ```

=== "命令行"

    ```bash
    python -m xtquant_manager --host 127.0.0.1 --port 8888
    ```

=== "Python 代码"

    ```python
    from xtquant_manager import XtQuantServer, XtQuantServerConfig
    from xtquant_manager import XtQuantManager, AccountConfig

    server = XtQuantServer(XtQuantServerConfig(
        host="127.0.0.1",
        port=8888,
    ))
    server.start(blocking=False)

    manager = XtQuantManager.get_instance()
    manager.register_account(AccountConfig(
        account_id="55009640",
        qmt_path="C:/QMT/userdata_mini",
    ))
    ```

## 验证

```bash
# 健康检查（无需 Token）
curl http://127.0.0.1:8888/api/v1/health

# 注册成功后查看账号状态
curl http://127.0.0.1:8888/api/v1/accounts/55009640/status
```

!!! note "账号注册时机"
    使用配置文件启动时，账号在服务启动时自动注册。
    使用命令行启动时，需通过 `POST /api/v1/accounts` 手动注册。
