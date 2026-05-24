# 安全配置

## 本机开发（无认证）

```json
{"host": "127.0.0.1", "port": 8888, "api_token": ""}
```

`/api/v1/health` 和 `/api/v1/health/{id}` 始终无需 Token，可直接用作存活探针。

---

## 局域网（Token + IP 白名单）

```json
{
  "host": "192.168.1.100",
  "port": 8888,
  "api_token": "at-least-32-char-random-string",
  "allowed_ips": ["192.168.1.0/24"],
  "rate_limit": 120
}
```

生成随机 Token：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## HTTPS（自签证书）

```bash
# 生成证书（包含 SAN for IP）
python xtquant_manager/utils/gen_cert.py --ip 192.168.1.100 --out certs/
```

```json
{
  "ssl_certfile": "certs/server.crt",
  "ssl_keyfile":  "certs/server.key"
}
```

客户端跳过证书验证（自签证书）：

```python
client = XtQuantClient(config=ClientConfig(
    base_url="https://192.168.1.100:8888",
    verify_ssl=False,
))
```

---

## HMAC 签名（公网/高安全）

```json
{"enable_hmac": true, "hmac_secret": "very-long-random-secret"}
```

Python 客户端生成签名请求头：

```python
from xtquant_manager.security import generate_hmac_headers

headers = generate_hmac_headers(
    method="GET",
    path="/api/v1/health",
    secret="very-long-random-secret",
)
```

---

## 安全级别对比

| 场景 | Token | IP 白名单 | HTTPS | HMAC |
|------|:-----:|:--------:|:-----:|:----:|
| 本机开发 | — | — | — | — |
| 局域网（受控内网） | ✓ | ✓ | — | — |
| 局域网（严格） | ✓ | ✓ | ✓ | — |
| 公网 | ✓ | ✓ | ✓ | ✓ |

---

## 隐私安全最佳实践

### 不硬编码凭证

所有 Token、密码、账号 ID 一律使用环境变量或配置文件，绝不写入源代码：

```python
# ✅ 正确：环境变量
token = os.environ.get("PUSHPLUS_TOKEN", "")

# ❌ 错误：硬编码
token = "65a7ae6c776c4881899e36aace47d491"
```

### 敏感文件保护

| 文件 | 保护方式 |
|------|---------|
| `account_config.json` | `.gitignore` 已排除，不提交到 Git |
| `xtquant_manager_config.json` | 包含 `api_token`，应加入 `.gitignore` |
| `web2.0/dist/` | 构建产物含编译后的前端代码，已加入 `.gitignore` |
| `web2.0/node_modules/` | 第三方依赖，已加入 `.gitignore` |

### 构建产物隐私

`web2.0/dist/` 中的 JavaScript bundle 会内联所有 `VITE_*` 环境变量。
不要将真实 Token 写入 `.env.production` 中提交。
改为在 UI 连接设置面板中运行时配置（保存到 localStorage）。

### 文档示例

文档中的示例账号 ID 统一使用虚构 ID（如 `55009640`），不使用真实账号。
