# 可观测性实战

## 指标解读

指标基于滑动窗口实时计算：延迟统计最近 1000 次，错误率统计最近 100 次。

| 指标 | 健康基准 | 告警阈值 |
|------|---------|---------|
| `error_rate` | 0 | > 0.01（1% 错误率） |
| `avg_latency_ms` | < 10ms | > 100ms |
| `p95_latency_ms` | < 50ms | > 500ms |
| `timeout_calls` | 0 | 连续出现 |

## 常用查询

```bash
# 快速健康快照
curl -s http://127.0.0.1:8888/api/v1/health | python -m json.tool

# 查看延迟分布
curl -s -H "X-API-Token: $TOKEN" \
  http://127.0.0.1:8888/api/v1/metrics/55009640 \
  | python -c "
import sys, json
d = json.load(sys.stdin)['data']
print(f\"avg={d['avg_latency_ms']}ms  p50={d['p50_latency_ms']}ms  p95={d['p95_latency_ms']}ms\")
print(f\"error_rate={d['error_rate']:.1%}  timeouts={d['timeout_calls']}\")
"
```

## 监控脚本

将以下脚本加入定时任务，每分钟检查一次：

```python
import httpx
import sys
import time

BASE = "http://127.0.0.1:8888/api/v1"
ALERT_ERROR_RATE = 0.01
ALERT_P95_MS = 500

resp = httpx.get(f"{BASE}/health", timeout=5)
if resp.status_code != 200:
    print(f"[CRITICAL] health 接口不可达: {resp.status_code}")
    sys.exit(2)

data = resp.json()["data"]
if data["healthy"] < data["total"]:
    disconnected = [k for k, v in data["accounts"].items() if not v["connected"]]
    print(f"[WARN] 账号断线: {disconnected}")

# 检查指标
metrics_resp = httpx.get(f"{BASE}/metrics", timeout=5)
if metrics_resp.status_code == 200:
    for acct, m in metrics_resp.json()["data"].items():
        if m["error_rate"] > ALERT_ERROR_RATE:
            print(f"[WARN] {acct} 错误率 {m['error_rate']:.1%}")
        if m["p95_latency_ms"] > ALERT_P95_MS:
            print(f"[WARN] {acct} P95 延迟 {m['p95_latency_ms']:.0f}ms")
```

## 日志文件位置

| 场景 | 日志路径 |
|------|---------|
| 管理脚本启动 | `logs/xqm_manager.log`（项目根目录） |
| 直接启动 | 标准输出（重定向到自定义路径） |

```bat
# 实时追踪日志
xtquant_manager\xqm_manager.bat logs
```
