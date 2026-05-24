"""
XtQuantManager 真实 QMT 只读功能测试

连接正在运行的 QMT 双账号（25105132 / 25106531），
仅执行 GET 只读端点，不下单，不修改任何持仓。

验证：
- QMT 真实连接成功（_connected=True）
- 多账号健康聚合
- 各账号独立持仓/资产查询
- 行情 tick 数据可用
- 委托/成交查询
- 指标采集
"""
import os
import sys
import time
import threading
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from xtquant_manager.manager import XtQuantManager
from xtquant_manager.account import AccountConfig
from xtquant_manager.server_runner import XtQuantServer, XtQuantServerConfig

ACC1 = "25105132"
ACC2 = "25106531"
BASE = "http://127.0.0.1:8800"

_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    flag = "PASS" if cond else "FAIL"
    print(f"  [{flag}] {name}" + (f"  -> {detail}" if detail else ""))


def wait_port(timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE}/api/v1/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    print("=" * 64)
    print("XtQuantManager 真实 QMT 只读功能测试")
    print(f"账号: {ACC1}, {ACC2}")
    print("=" * 64)

    # 1. 注册真实账号到 XtQuantManager
    XtQuantManager.reset_instance()
    manager = XtQuantManager.get_instance()

    print("\n-- 注册真实 QMT 账号 --")
    for acc_id, qmt_path in [(ACC1, "C:/QMT/userdata_mini"), (ACC2, "C:/QMT1/userdata_mini")]:
        cfg = AccountConfig(
            account_id=acc_id,
            qmt_path=qmt_path,
            account_type="STOCK",
            call_timeout=5.0,
            connect_timeout=15.0,
            reconnect_base_wait=60.0,
            max_reconnect_attempts=3,
        )
        ok = manager.register_account(cfg)
        check(f"注册 {acc_id[:4]}*** (path={qmt_path[-20:]})", ok, "connected" if ok else "failed")

    # 2. 启动 HTTP 服务
    print("\n-- 启动 HTTP 服务 (端口 8800) --")
    server = XtQuantServer(XtQuantServerConfig(host="127.0.0.1", port=8800))
    server.start(blocking=False)
    if not wait_port():
        check("服务在 8800 启动并可达", False, "超时未就绪")
        server.stop(timeout=5.0)
        _report()
        return
    check("服务在 8800 启动并可达", True)

    try:
        # 3. 健康检查聚合
        print("\n-- 健康状态 /health --")
        r = httpx.get(f"{BASE}/api/v1/health")
        d = r.json().get("data", {})
        check("GET /health 返回 200", r.status_code == 200)
        check("/health total=2", d.get("total") == 2, f"total={d.get('total')}")
        healthy = d.get("healthy", 0)
        check("/health healthy>=1 (至少一连通)", healthy >= 1, f"healthy={healthy}")
        accounts_state = d.get("accounts", {})
        for aid in [ACC1, ACC2]:
            st = accounts_state.get(aid, {})
            print(f"    {aid[:4]}*** : connected={st.get('connected')}, "
                  f"xtdata={st.get('xtdata_available')}, xttrader={st.get('xttrader_available')}")

        # 4. 单账号状态
        print("\n-- 单账号状态 --")
        for aid in [ACC1, ACC2]:
            r = httpx.get(f"{BASE}/api/v1/accounts/{aid}/status")
            s = r.json().get("data", {})
            check(f"{aid[:4]}*** status 200", r.status_code == 200)
            check(f"{aid[:4]}*** account_id 匹配", s.get("account_id") == aid)

        # 5. 持仓查询（多账号隔离）
        print("\n-- 持仓查询 /positions --")
        positions_by_acc = {}
        for aid in [ACC1, ACC2]:
            r = httpx.get(f"{BASE}/api/v1/accounts/{aid}/positions")
            check(f"{aid[:4]}*** positions 200", r.status_code == 200, f"status={r.status_code}")
            ps = r.json().get("data", {}).get("positions", [])
            positions_by_acc[aid] = ps
            if ps:
                codes = [p.get("证券代码", "?") for p in ps[:5]]
                print(f"    {aid[:4]}*** : {len(ps)} 只持仓, 前5: {codes}")
            else:
                print(f"    {aid[:4]}*** : 空仓")
        # 验证隔离：两个账号的持仓不应有交叉（除非实际持有相同股票）
        codes1 = {p.get("证券代码") for p in positions_by_acc.get(ACC1, [])}
        codes2 = {p.get("证券代码") for p in positions_by_acc.get(ACC2, [])}
        print(f"    ACC1 持仓代码: {codes1}")
        print(f"    ACC2 持仓代码: {codes2}")

        # 6. 资产查询
        print("\n-- 资产查询 /asset --")
        for aid in [ACC1, ACC2]:
            r = httpx.get(f"{BASE}/api/v1/accounts/{aid}/asset")
            check(f"{aid[:4]}*** asset 200", r.status_code == 200)
            asset = r.json().get("data", {})
            if asset:
                print(f"    {aid[:4]}*** : 总资产={asset.get('总资产', '?')}, "
                      f"可用={asset.get('可用金额', '?')}, 市值={asset.get('持仓市值', '?')}")

        # 7. 行情 tick（真实数据）
        print("\n-- 行情 tick /market/tick --")
        test_codes = "000001.SZ,600036.SH"
        r = httpx.get(f"{BASE}/api/v1/market/tick",
                      params={"stock_codes": test_codes, "account_id": ACC1})
        check("GET /market/tick 200", r.status_code == 200, f"status={r.status_code}")
        tick_data = r.json().get("data", {})
        for code in test_codes.split(","):
            has_data = code in tick_data and tick_data[code] is not None and len(str(tick_data[code])) > 5
            check(f"tick {code} 有数据", has_data,
                  f"keys={list(tick_data.keys()) if tick_data else 'empty'}")

        # 8. 委托/成交查询（非交易时段可能为空）
        print("\n-- 委托/成交查询 --")
        for aid in [ACC1, ACC2]:
            for ep in ["orders", "trades"]:
                r = httpx.get(f"{BASE}/api/v1/accounts/{aid}/{ep}")
                ok = r.status_code == 200 and r.json().get("success")
                data_key = ep
                items = r.json().get("data", {}).get(data_key, [])
                check(f"{aid[:4]}*** GET /{ep} 成功", ok,
                      f"count={len(items) if isinstance(items, list) else 'N/A'}")

        # 9. 指标采集
        print("\n-- 指标 /metrics --")
        r = httpx.get(f"{BASE}/api/v1/metrics")
        check("GET /metrics 200", r.status_code == 200)
        all_m = r.json().get("data", {})
        check("/metrics 含两个账号", ACC1 in all_m and ACC2 in all_m,
              f"keys={list(all_m.keys())}")
        for aid in [ACC1, ACC2]:
            r = httpx.get(f"{BASE}/api/v1/metrics/{aid}")
            check(f"{aid[:4]}*** GET /metrics 200", r.status_code == 200)

        # 10. 错误路径
        print("\n-- 错误路径 --")
        r = httpx.get(f"{BASE}/api/v1/accounts/99999999/status")
        check("不存在账号 404", r.status_code == 404)

        # 11. 历史行情（带真实账号）
        print("\n-- 历史行情 /market/history --")
        r = httpx.get(f"{BASE}/api/v1/market/history", params={
            "stock_code": "000001.SZ",
            "account_id": ACC1,
            "period": "1d",
            "start_time": "20260520",
            "end_time": "20260523",
        })
        check("GET /market/history 200", r.status_code == 200)
        hist_data = r.json().get("data", {})
        check("历史数据非空", bool(hist_data), f"keys={list(hist_data.keys()) if hist_data else 'empty'}")

    finally:
        print("\n-- 关闭服务 --")
        server.stop(timeout=10.0)
        manager.shutdown()
        print("服务已关闭")

    _report()


def _report():
    print("\n" + "=" * 64)
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    failed = [name for name, ok, _ in _results if not ok]
    print(f"汇总: {passed}/{total} 通过")
    if failed:
        print("失败项:")
        for name in failed:
            print(f"  - {name}")
    else:
        print("ALL TESTS PASSED")
    print("=" * 64)


if __name__ == "__main__":
    main()
