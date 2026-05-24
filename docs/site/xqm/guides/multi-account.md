# 多账号实战

## 实例一：双账号独立交易

账号 A（55009640）做网格交易，账号 B（55009641）做止盈止损，互不干扰。

```python
from xtquant_manager.client import XtQuantClient, ClientConfig

client_a = XtQuantClient(config=ClientConfig(
    base_url="http://127.0.0.1:8888",
    account_id="55009640",
))
client_b = XtQuantClient(config=ClientConfig(
    base_url="http://127.0.0.1:8888",
    account_id="55009641",
))

pos_a = client_a.position()
pos_b = client_b.position()

balance_a = client_a.balance()
balance_b = client_b.balance()

print(f"账号A总资产: {balance_a['总资产'].iloc[0]:,.2f}")
print(f"账号B总资产: {balance_b['总资产'].iloc[0]:,.2f}")
```

---

## 实例二：运行时动态注册账号

已有服务在运行，无需重启，通过 API 注册新账号：

```bash
# 当前只有账号 A
curl http://127.0.0.1:8888/api/v1/accounts
# {"data":{"accounts":["55009640"]}}

# 动态注册账号 B
curl -X POST http://127.0.0.1:8888/api/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "55009641",
    "qmt_path": "C:/QMT1/userdata_mini",
    "account_type": "STOCK"
  }'
# {"data":{"account_id":"55009641","connected":true,"message":"注册成功"}}

# 确认两个账号
curl http://127.0.0.1:8888/api/v1/accounts
# {"data":{"accounts":["55009640","55009641"]}}
```

---

## 实例三：多账号资产汇总

```python
import httpx

BASE = "http://127.0.0.1:8888/api/v1"

def print_all_assets():
    accounts = httpx.get(f"{BASE}/accounts").json()["data"]["accounts"]

    total_asset = 0.0
    total_market_value = 0.0

    for account_id in accounts:
        resp = httpx.get(f"{BASE}/accounts/{account_id}/asset").json()
        if resp["success"]:
            asset = resp["data"]
            total_asset += asset.get("总资产", 0)
            total_market_value += asset.get("持仓市值", 0)
            print(f"  [{account_id}] 总资产: {asset['总资产']:>12,.2f}  "
                  f"持仓市值: {asset['持仓市值']:>12,.2f}  "
                  f"可用资金: {asset['可用金额']:>12,.2f}")

    print(f"\n  汇总: 总资产 {total_asset:,.2f}  持仓市值 {total_market_value:,.2f}")

print_all_assets()
```

---

## 实例四：多账号并行下单

```python
import httpx
import concurrent.futures

BASE = "http://127.0.0.1:8888/api/v1"

def place_order(account_id, stock_code, order_type, volume, price):
    resp = httpx.post(
        f"{BASE}/accounts/{account_id}/orders",
        json={
            "stock_code": stock_code,
            "order_type": order_type,
            "order_volume": volume,
            "price_type": 11,
            "price": price,
        },
        timeout=10,
    ).json()
    return account_id, resp

# 两账号同时买入同一只股票
orders = [
    ("55009640", "000001.SZ", 23, 100, 10.50),
    ("55009641", "000001.SZ", 23, 200, 10.50),
]

with concurrent.futures.ThreadPoolExecutor() as pool:
    futures = [pool.submit(place_order, *o) for o in orders]
    for f in concurrent.futures.as_completed(futures):
        account_id, result = f.result()
        order_id = result["data"].get("order_id", "FAILED")
        print(f"账号 {account_id}: order_id = {order_id}")
```

---

## 实例五：健康监控循环

```python
import httpx
import time

BASE = "http://127.0.0.1:8888/api/v1"
CHECK_INTERVAL = 30

def check_health():
    resp = httpx.get(f"{BASE}/health", timeout=5).json()
    data = resp["data"]
    print(f"[{time.strftime('%H:%M:%S')}] 账号总数: {data['total']}  "
          f"健康: {data['healthy']}")
    for acct_id, state in data["accounts"].items():
        status = "OK" if state["connected"] else "DISCONNECTED"
        retries = state.get("reconnect_attempts", 0)
        print(f"  {acct_id}: {status}"
              + (f"  (重连次数: {retries})" if retries else ""))
    if data["healthy"] < data["total"]:
        print("  [ALERT] 有账号断线，请检查 QMT 客户端")

while True:
    check_health()
    time.sleep(CHECK_INTERVAL)
```
