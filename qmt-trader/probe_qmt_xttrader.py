# probe_qmt_xttrader.py
# ─────────────────────────────────────────────────────────────────────────────
# 独立 Python「xttrader 连通性快速探针」——在大QMT机器的普通 Python(Anaconda)里运行，
# 验证 miniQMT/xttrader 交易通道是否可连接、可登录、可查询（现有 easy_qmt_trader / IPC
# executor 都依赖这条通道）。
#
# ⚠️ 全程只读，绝不下单。
#
# 用法（大QMT机器上）：
#   python qmt-trader/probe_qmt_xttrader.py
#   python qmt-trader/probe_qmt_xttrader.py --path "C:/光大证券金阳光QMT实盘/userdata_mini" --account 12345678
#
# 账号/路径来源优先级：命令行参数 > 项目 account_config.json/config > 文件顶部默认值。
# 前置：QMT 客户端已启动并登录（极简模式=行情+交易）。
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
import time
import json
import argparse
import traceback

# 控制台/日志可能是 GBK，尽力切到 UTF-8 并对不可编码字符降级，避免打印崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 允许脱离项目独立运行；能 import 项目 config 时复用其账号/路径
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DEFAULT_PATH = r"C:\光大证券金阳光QMT实盘\userdata_mini"
DEFAULT_ACCOUNT = "你的资金账号"
DEFAULT_ACCOUNT_TYPE = "STOCK"


def resolve_config(args):
    """确定 path/account/account_type：CLI > 项目config > account_config.json > 默认。"""
    path = args.path
    account = args.account
    account_type = args.account_type or DEFAULT_ACCOUNT_TYPE

    # 尝试项目 config
    if not (path and account):
        try:
            import config
            acc_cfg = config.get_account_config()
            path = path or getattr(config, "QMT_PATH", None) or acc_cfg.get("qmt_path")
            account = account or acc_cfg.get("account_id")
            account_type = account_type or acc_cfg.get("account_type", "STOCK")
        except Exception:
            pass

    # 尝试 account_config.json
    if not (path and account):
        cfg_path = os.path.join(_ROOT, "account_config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    j = json.load(f)
                path = path or j.get("qmt_path")
                account = account or j.get("account_id")
                account_type = account_type or j.get("account_type", "STOCK")
            except Exception:
                pass

    return path or DEFAULT_PATH, account or DEFAULT_ACCOUNT, account_type


def main():
    ap = argparse.ArgumentParser(description="大QMT xttrader 只读连通性探针")
    ap.add_argument("--path", help="userdata_mini 路径")
    ap.add_argument("--account", help="资金账号")
    ap.add_argument("--account-type", dest="account_type", help="账号类型(默认STOCK)")
    ap.add_argument("--timeout", type=int, default=30, help="连接超时秒(默认30)")
    args = ap.parse_args()

    path, account, account_type = resolve_config(args)

    print("=" * 60)
    print("大QMT xttrader 只读连通性探针")
    print("=" * 60)
    print(f"userdata_mini 路径 : {path}")
    print(f"资金账号           : {account}")
    print(f"账号类型           : {account_type}")
    print(f"路径存在           : {os.path.isdir(path)}")
    print("-" * 60)

    if not os.path.isdir(path):
        print("[NG] 路径不存在，请用 --path 指定正确的 userdata_mini 目录")
        return 2
    if not account or account == "你的资金账号":
        print("[NG] 未提供资金账号，请用 --account 指定，或配置 account_config.json")
        return 2

    # 1) import
    try:
        from xtquant.xttrader import XtQuantTrader
        from xtquant.xttype import StockAccount
        print("[OK] import xtquant.xttrader 成功")
    except Exception as e:
        print(f"[NG] import xtquant.xttrader 失败: {e}")
        print("  → 本 Python 环境缺少 xtquant 交易模块（miniQMT 未装或环境不对）")
        return 3

    xt = None
    connected = query_ok = False
    try:
        # 2) connect（带超时保护，避免卡死）
        session_id = int(time.time()) % 1000000
        xt = XtQuantTrader(path, session_id)
        xt.start()

        import threading
        rc = {"v": None, "err": None}

        def _c():
            try:
                rc["v"] = xt.connect()
            except Exception as e:
                rc["err"] = e

        t = threading.Thread(target=_c, daemon=True)
        t.start()
        t.join(args.timeout)
        if t.is_alive():
            print(f"[NG] connect() 超时（{args.timeout}秒）——QMT 未启动/未登录或路径不对")
            return 4
        if rc["err"]:
            print(f"[NG] connect() 异常: {rc['err']}")
            return 4
        print(f"connect() 返回码: {rc['v']}（0=成功）")
        connected = (rc["v"] == 0)
        if not connected:
            print("[NG] 交易连接失败：请确认 QMT 已登录且开启【极简模式(行情+交易)】")
            return 4

        acc = StockAccount(account, account_type)
        sub = xt.subscribe(acc)
        print(f"subscribe() 返回码: {sub}")

        # 3) 只读查询资产
        asset = xt.query_stock_asset(acc)
        if asset is not None:
            print(f"[OK] 资产查询成功: 总资产={getattr(asset,'total_asset','?'):.2f}  "
                  f"可用={getattr(asset,'cash','?'):.2f}  "
                  f"持仓市值={getattr(asset,'market_value','?'):.2f}")
            query_ok = True
        else:
            print("[NG] 资产查询返回 None（账号可能未授权/未在此 QMT 登录）")

        # 4) 只读查询持仓
        positions = xt.query_stock_positions(acc)
        n = len(positions) if positions else 0
        print(f"[OK] 持仓查询成功: 持仓 {n} 只")
        for p in (positions or [])[:5]:
            print(f"    {getattr(p,'stock_code','?')}  "
                  f"数量={getattr(p,'volume','?')}  "
                  f"可用={getattr(p,'can_use_volume','?')}  "
                  f"成本={getattr(p,'open_price','?')}")
    except Exception as e:
        print(f"[NG] 探测异常: {e}")
        print(traceback.format_exc())
    finally:
        try:
            if xt is not None:
                xt.stop()
        except Exception:
            pass

    print("-" * 60)
    if connected and query_ok:
        print(">> 结论: xttrader 通道【可用】——现有 IPC executor(xttrader) / easy_qmt_trader 可直接使用")
        return 0
    print(">> 结论: xttrader 通道【不可用/不完整】——见上方逐项。若 QMT 已登录仍失败，")
    print("        可能券商未授权 miniQMT，请再跑 probe_qmt_authorization.py 看 passorder 是否可用")
    return 1


if __name__ == "__main__":
    sys.exit(main())
