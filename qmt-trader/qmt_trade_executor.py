# qmt_trade_executor.py
# 大QMT文件IPC方案 — QMT侧执行脚本（多账号版）
# 放在 QMT 的 Python 脚本目录，设为定时运行模式，周期 1000ms
#
# 多账号支持：
#   策略端(miniQMT)每个账号一个进程，各自把订单写入 IPC_ROOT/{account_id}/ 子目录，
#   并在该子目录写入 config.json（含 account_id + qmt_path）。
#   本脚本自动扫描 IPC_ROOT 下所有账号子目录，逐个处理，无需为每个账号改脚本。
#
# 配置方式：
#   方式A（推荐，零手改）：策略端自动生成各账号子目录的 config.json，本脚本自动读取。
#       首次运行前只需在各账号的 config.json 里填大QMT的 qmt_path（同券商多账号填同一个路径）。
#       同券商两个账号只需要一个大QMT：executor 按 qmt_path 复用同一个 xttrader 连接，
#       然后逐一 trader.login(account_id) 即可同时管理多个资金账号。
#   方式B（手动）：修改下方 _DEFAULT_ACCOUNT_ID / _DEFAULT_QMT_PATH（仅用于无 config.json 的兜底）。
#
# 部署拓扑：
#   - 同券商多账号：一个大QMT + 一个 executor 进程，自动处理所有账号。
#   - 不同券商各一个账号：每大QMT跑一个 executor，用 QMT_IPC_ACCOUNT_FILTER 隔离。
#   - 当前项目（光大证券 25105132 + 25106531）：只需一个大QMT，一个 executor。

import os
import json
import time
import shutil
import traceback
from datetime import datetime

IPC_ROOT = r"C:\QuantIPC"
DIR_LOG = os.path.join(IPC_ROOT, "qmt_log")

# 无 config.json 时的兜底默认值（方式B）。正常使用时策略端会写入 config.json，此默认值不生效。
_DEFAULT_ACCOUNT_ID = "你的资金账号"
# ⚠️ 大QMT的 userdata_mini 目录。同券商两个账号只需一个大QMT，填此路径后即可同时管理两个资金账号。
# -- 示例（光大证券）：r"C:/光大证券金阳光QMT实盘/userdata_mini"
_DEFAULT_QMT_PATH = r"C:\光大证券金阳光QMT实盘\userdata_mini"

# 账号过滤（多个大QMT各跑一个 executor 时用；空=处理全部账号）
ACCOUNT_FILTER = os.environ.get("QMT_IPC_ACCOUNT_FILTER", "").strip()

os.makedirs(DIR_LOG, exist_ok=True)

# 连接池：qmt_path -> XtQuantTrader（相同大QMT路径的账号复用同一连接）
_traders = {}
# 已 login 的账号集合：(qmt_path, account_id)
_logged_in = set()


def log(msg):
    path = os.path.join(DIR_LOG, f"log_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S.%f')[:12]}] {msg}\n")


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _account_dirs(acc_dir):
    """返回一个账号目录下的各子目录路径，并确保存在。"""
    dirs = {
        "pending": os.path.join(acc_dir, "orders", "pending"),
        "processing": os.path.join(acc_dir, "orders", "processing"),
        "done": os.path.join(acc_dir, "orders", "done"),
        "cancel": os.path.join(acc_dir, "cancel"),
        "status": os.path.join(acc_dir, "status"),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def discover_accounts():
    """
    扫描 IPC_ROOT 下所有账号子目录（每个含 config.json）。

    Returns:
        list[dict]: [{"account_id", "qmt_path", "dir", "dirs"}, ...]
    """
    accounts = []
    if not os.path.isdir(IPC_ROOT):
        return accounts

    filt = None
    if ACCOUNT_FILTER:
        filt = set(a.strip() for a in ACCOUNT_FILTER.split(",") if a.strip())

    for name in sorted(os.listdir(IPC_ROOT)):
        sub = os.path.join(IPC_ROOT, name)
        if not os.path.isdir(sub):
            continue
        cfg = _load_json(os.path.join(sub, "config.json"))
        if not cfg:
            continue  # 只处理策略端已写入 config.json 的账号目录
        account_id = cfg.get("account_id") or name
        qmt_path = cfg.get("qmt_path") or _DEFAULT_QMT_PATH
        if filt and account_id not in filt:
            continue
        accounts.append({
            "account_id": account_id,
            "qmt_path": qmt_path,
            "dir": sub,
            "dirs": _account_dirs(sub),
        })

    # 兼容旧的单账号扁平结构：IPC_ROOT 直接含 orders/（无账号子目录）
    if not accounts and os.path.isdir(os.path.join(IPC_ROOT, "orders")):
        accounts.append({
            "account_id": _DEFAULT_ACCOUNT_ID,
            "qmt_path": _DEFAULT_QMT_PATH,
            "dir": IPC_ROOT,
            "dirs": _account_dirs(IPC_ROOT),
        })
    return accounts


def get_trader(qmt_path):
    """按大QMT路径复用/建立 xttrader 连接。"""
    if _traders.get(qmt_path) is None:
        try:
            from xtquant import xttrader
            trader = xttrader.XtQuantTrader(
                mini_qmt_path=qmt_path,
                session_id=(int(time.time()) % 100000) + len(_traders)
            )
            trader.connect()
            _traders[qmt_path] = trader
            log(f"xttrader 连接成功 (path={qmt_path})")
        except Exception as e:
            log(f"xttrader 连接失败 (path={qmt_path}): {e}")
            return None
    return _traders[qmt_path]


def ensure_login(trader, qmt_path, account_id):
    """确保账号已登录（每个 (qmt_path, account_id) 只 login 一次）。"""
    key = (qmt_path, account_id)
    if key in _logged_in:
        return
    try:
        trader.login(account_id)
        _logged_in.add(key)
        log(f"账号登录成功: {account_id}")
    except Exception as e:
        log(f"账号登录失败 {account_id}: {e}")


def write_result(done_dir, processing_path, order, status, msg, filled_price=0, filled_vol=0):
    """写成交回执到该账号的 done 目录。"""
    result = {
        "version": "1.0",
        "order_id": order["order_id"],
        "orig_timestamp": order.get("timestamp", ""),
        "exec_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:23],
        "status": status,
        "action": order.get("action", ""),
        "stock_code": order.get("stock_code", ""),
        "filled_price": filled_price,
        "filled_volume": filled_vol,
        "total_volume": order["volume"],
        "strategy": order.get("strategy", ""),
        "remark": order.get("remark", ""),
        "error": msg if status in ("rejected", "error", "cancelled_by_user") else None,
    }
    done_path = os.path.join(done_dir, os.path.basename(processing_path))
    with open(done_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    try:
        os.remove(processing_path)
    except Exception:
        pass


def process_order(acc, filepath):
    """处理一个账号的一个下单文件。acc 是 discover_accounts() 的元素。"""
    dirs = acc["dirs"]
    account_id = acc["account_id"]
    filename = os.path.basename(filepath)
    order = None
    try:
        # 原子取走：pending → processing
        processing_path = os.path.join(dirs["processing"], filename)
        shutil.move(filepath, processing_path)

        with open(processing_path, "r", encoding="utf-8") as f:
            order = json.load(f)

        order_id = order["order_id"]
        log(f"[{account_id}] 处理 {order_id}: {order['action']} {order['stock_code']} {order['volume']}股")

        # 撤单检查
        cancel_path = os.path.join(dirs["cancel"], f"cancel_{order_id}.json")
        if os.path.exists(cancel_path):
            write_result(dirs["done"], processing_path, order, "cancelled", "用户撤单")
            os.remove(cancel_path)
            return

        trader = get_trader(acc["qmt_path"])
        if trader is None:
            write_result(dirs["done"], processing_path, order, "rejected", "xttrader未连接")
            return
        ensure_login(trader, acc["qmt_path"], account_id)

        from xtquant import xtconstant
        xt_action = xtconstant.STOCK_BUY if order["action"] == "buy" else xtconstant.STOCK_SELL

        # 下单：传入本账号 account_id（多账号隔离的关键）
        if order.get("price_type") == "market":
            seq = trader.order_stock(account_id, order["stock_code"], xt_action,
                                     order["volume"], xtconstant.FIX_PRICE, 0, xtconstant.LATEST_PRICE)
        else:
            seq = trader.order_stock(account_id, order["stock_code"], xt_action,
                                     order["volume"], xtconstant.FIX_PRICE, order["price"])

        log(f"[{account_id}] 委托序号={seq}")

        # 轮询等待成交
        timeout = order.get("timeout_sec", 30)
        deadline = time.time() + timeout
        result = None
        while time.time() < deadline:
            time.sleep(0.5)
            orders = trader.query_all_orders(account_id)
            for o in orders:
                if str(o.order_id) == str(seq):
                    if o.order_status == xtconstant.ORDER_ALL_TRADED:
                        result = {"status": "filled", "price": o.traded_price, "vol": o.traded_vol}
                    elif o.order_status in (xtconstant.ORDER_PART_TRADED, xtconstant.ORDER_PART_TRADED_CANCELED):
                        result = {"status": "partial", "price": o.traded_price, "vol": o.traded_vol}
                    elif o.order_status == xtconstant.ORDER_CANCELED:
                        result = {"status": "cancelled", "price": 0, "vol": 0}
                    break
            if result:
                break

        if result is None:
            trader.cancel_order(account_id, seq)
            result = {"status": "cancelled_timeout", "price": 0, "vol": 0}
            log(f"[{account_id}] 订单 {order_id} 超时({timeout}秒)已撤单")

        write_result(dirs["done"], processing_path, order, result["status"],
                     f"成交价={result['price']}, 量={result['vol']}",
                     filled_price=result["price"], filled_vol=result["vol"])

    except Exception as e:
        log(f"[{account_id}] 异常: {e}\n{traceback.format_exc()}")
        if order:
            write_result(dirs["done"], processing_path, order, "error", str(e))


def update_account_status(acc):
    """写某账号的持仓/资金快照到其 status/account.json。"""
    account_id = acc["account_id"]
    try:
        trader = get_trader(acc["qmt_path"])
        if not trader:
            return
        ensure_login(trader, acc["qmt_path"], account_id)
        account = trader.query_account(account_id)
        positions = trader.query_stock_positions(account_id)
        snapshot = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account_id": account_id,
            "total_asset": account.total_asset,
            "available": account.available,
            "market_value": account.market_value,
            "frozen": account.frozen_cash,
            "positions": [{"stock": p.stock_code, "volume": p.volume,
                           "available": getattr(p, "can_use_volume", p.volume),
                           "cost": p.open_price,
                           "market_price": p.market_price,
                           "market_value": getattr(p, "market_value", p.market_price * p.volume)}
                          for p in positions],
            "today_pnl": account.pnl
        }
        with open(os.path.join(acc["dirs"]["status"], "account.json"), "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def process_account(acc, update_snapshot):
    """处理单个账号：写心跳 + 处理 pending + 定时写账户快照。"""
    dirs = acc["dirs"]
    # 心跳
    with open(os.path.join(dirs["status"], "heartbeat.json"), "w") as f:
        json.dump({"ts": datetime.now().isoformat(), "account_id": acc["account_id"]}, f)

    # 处理待下单文件（每账号每轮最多 5 个）
    pending = sorted([f for f in os.listdir(dirs["pending"])
                      if f.endswith(".json") and not f.startswith(".")])
    for filename in pending[:5]:
        filepath = os.path.join(dirs["pending"], filename)
        if os.path.exists(filepath):
            process_order(acc, filepath)

    if update_snapshot:
        update_account_status(acc)


def main():
    """QMT定时运行入口：遍历所有账号子目录。"""
    if not hasattr(main, "_counter"):
        main._counter = 0
    main._counter += 1
    update_snapshot = (main._counter % 30 == 0)  # 每30轮刷一次账户快照

    accounts = discover_accounts()
    if not accounts:
        log("未发现任何账号目录（等待策略端写入 config.json）")
        return
    for acc in accounts:
        try:
            process_account(acc, update_snapshot)
        except Exception as e:
            log(f"[{acc.get('account_id')}] process_account 异常: {e}")


if __name__ == "__main__":
    main()
