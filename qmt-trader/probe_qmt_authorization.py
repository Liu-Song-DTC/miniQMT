# probe_qmt_authorization.py
# -----------------------------------------------------------------------------
# Big-QMT strategy-side AUTHORIZATION PROBE. Detects which trading channel the
# current QMT Python strategy environment is authorized for:
#   (1) VBA built-in API : passorder / cancel / get_trade_detail_data
#   (2) miniQMT xttrader : from xtquant import xttrader -> XtQuantTrader().connect()
#
# READ-ONLY. NEVER places an order. `passorder` is only checked for existence
# (callable), it is NEVER actually called.
#
# ASCII-ONLY on purpose: the QMT strategy editor stores files as GBK, so any
# non-ASCII (Chinese) byte breaks Python's UTF-8 source decoding. Keep this
# file pure ASCII so it compiles/runs in the QMT editor regardless of encoding.
#
# HOW TO RUN (both modes supported, auto-adapted):
#   A. Timed-run mode (same as qmt_trade_executor.py deployment, most realistic):
#      QMT -> Strategy -> Python strategy -> new "timed run", pick this file,
#      period e.g. 5000ms, run once. See QMT log + C:\QuantIPC\probe_result.txt
#   B. Model-trading mode (init/handlebar, best when passorder needs ContextInfo):
#      QMT -> Strategy -> new "model trading", load this file, run.
#
# Before running: set ACCOUNT_ID below to your fund account.
# -----------------------------------------------------------------------------

import os
import json
import time
import traceback
from datetime import datetime

# Console/QMT log may be GBK; best-effort switch stdout to utf-8 (out() also guards)
try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============ set your fund account here ============
ACCOUNT_ID = "YOUR_ACCOUNT"
# If the account lives in C:\QuantIPC\{account}\config.json, leave default to auto-read
# ====================================================

# userdata_mini path (under big-QMT install dir), used by the xttrader probe.
QMT_USERDATA_MINI = r"C:\QMT\userdata_mini"

RESULT_FILE = r"C:\QuantIPC\probe_result.txt"

_probed = {"done": False}   # avoid repeated probing on every handlebar


def out(msg):
    """Print + append to result file (QMT log may truncate; file is reliable)."""
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line)
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(RESULT_FILE), exist_ok=True)
        with open(RESULT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _lookup(name):
    """Find a symbol injected by QMT into the strategy namespace (globals/builtins)."""
    g = globals().get(name)
    if g is not None:
        return g
    b = __builtins__
    if isinstance(b, dict):
        return b.get(name)
    return getattr(b, name, None)


def _resolve_account():
    """Account to probe: constant first, else first config.json under C:\\QuantIPC."""
    if ACCOUNT_ID and ACCOUNT_ID != "YOUR_ACCOUNT":
        return ACCOUNT_ID
    root = r"C:\QuantIPC"
    try:
        for name in sorted(os.listdir(root)):
            cfg = os.path.join(root, name, "config.json")
            if os.path.exists(cfg):
                with open(cfg, encoding="utf-8") as f:
                    acc = json.load(f).get("account_id")
                if acc:
                    return acc
    except Exception:
        pass
    return ACCOUNT_ID


# ---- Channel 1: VBA built-in API (passorder / get_trade_detail_data) ----
def probe_vba(account, ContextInfo=None):
    out("== Channel 1: VBA built-in API (passorder / get_trade_detail_data) ==")
    passorder = _lookup("passorder")
    cancel = _lookup("cancel")
    get_tdd = _lookup("get_trade_detail_data")

    out("  passorder callable: %s" % callable(passorder))
    out("  cancel    callable: %s" % callable(cancel))
    out("  get_trade_detail_data callable: %s" % callable(get_tdd))

    # Some QMT versions expose it as a ContextInfo method
    ctx_get_tdd = getattr(ContextInfo, "get_trade_detail_data", None) if ContextInfo is not None else None
    if callable(ctx_get_tdd):
        out("  ContextInfo.get_trade_detail_data callable: True")

    reader = get_tdd or ctx_get_tdd
    account_ok = False
    if callable(reader):
        # Read account cash (datatype case/args differ by version; try several)
        for args in [(account, "STOCK", "ACCOUNT"),
                     (account, "stock", "account"),
                     (account, "ACCOUNT")]:
            try:
                data = reader(*args)
                if data:
                    obj = data[0]
                    bal = getattr(obj, "m_dBalance", getattr(obj, "m_dTotalAsset", "?"))
                    avail = getattr(obj, "m_dAvailable", "?")
                    out("  [OK] VBA read account ok args=%s: total~%s avail~%s" % (args, bal, avail))
                    account_ok = True
                    break
            except Exception:
                continue
        if not account_ok:
            out("  [NG] get_trade_detail_data exists but reading account failed "
                "(account not logged in / arg format differs)")

        # Read positions
        for args in [(account, "STOCK", "POSITION"), (account, "POSITION")]:
            try:
                pos = reader(*args)
                out("  [OK] VBA read positions ok args=%s: count=%s" % (args, len(pos) if pos else 0))
                break
            except Exception:
                continue

    verdict = callable(passorder) and callable(reader)
    out("  >> VBA channel verdict: %s" % ("USABLE (passorder + account read present)"
                                          if verdict else "NOT usable / incomplete"))
    return {"passorder": callable(passorder), "get_trade_detail_data": callable(reader),
            "account_read": account_ok, "usable": verdict}


# ---- Channel 2: miniQMT xttrader ----
def probe_xttrader(account):
    out("== Channel 2: miniQMT xttrader (XtQuantTrader.connect/query) ==")
    result = {"import": False, "connect": False, "query": False, "usable": False}
    try:
        from xtquant.xttrader import XtQuantTrader
        from xtquant.xttype import StockAccount
        result["import"] = True
        out("  [OK] import xtquant.xttrader ok")
    except Exception as e:
        out("  [NG] import xtquant.xttrader failed: %s" % e)
        out("  >> xttrader channel verdict: NOT usable (no xtquant / miniQMT trade module here)")
        return result

    xt = None
    try:
        session_id = int(time.time()) % 1000000
        xt = XtQuantTrader(QMT_USERDATA_MINI, session_id)
        xt.start()
        # connect with timeout so it never hangs outside a real QMT env
        import threading
        box = {"rc": None, "err": None}

        def _do_connect():
            try:
                box["rc"] = xt.connect()
            except Exception as e:
                box["err"] = e

        th = threading.Thread(target=_do_connect, daemon=True)
        th.start()
        th.join(20)
        if th.is_alive():
            out("  [NG] connect() timeout(20s) -- not a QMT env or QMT not logged in")
            result["usable"] = False
            out("  >> xttrader channel verdict: NOT usable / incomplete")
            return result
        if box["err"]:
            raise box["err"]
        rc = box["rc"]
        out("  connect() rc: %s (0=success)" % rc)
        result["connect"] = (rc == 0)
        if rc == 0:
            acc = StockAccount(account, "STOCK")
            sub = xt.subscribe(acc)
            out("  subscribe() rc: %s" % sub)
            asset = xt.query_stock_asset(acc)
            if asset is not None:
                out("  [OK] query_stock_asset ok: total=%s avail=%s"
                    % (getattr(asset, "total_asset", "?"), getattr(asset, "cash", "?")))
                result["query"] = True
            positions = xt.query_stock_positions(acc)
            out("  [OK] query_stock_positions ok: count=%s" % (len(positions) if positions else 0))
    except Exception as e:
        out("  [NG] xttrader probe error: %s" % e)
        out(traceback.format_exc())
    finally:
        try:
            if xt is not None:
                xt.stop()
        except Exception:
            pass

    result["usable"] = result["connect"] and result["query"]
    out("  >> xttrader channel verdict: %s" % ("USABLE (connect + query ok)"
                                               if result["usable"] else "NOT usable / incomplete"))
    return result


def _final_verdict(vba, xtt):
    out("===================== FINAL VERDICT =====================")
    v, x = vba["usable"], xtt["usable"]
    if v and x:
        out("Both channels usable: current qmt_trade_executor.py (xttrader) deployable;")
        out("passorder also available as future backup if xttrader gets restricted.")
    elif x and not v:
        out("Only xttrader usable: current qmt_trade_executor.py (xttrader) deployable,")
        out("no passorder rework needed.")
    elif v and not x:
        out("Only passorder(VBA) usable: current xttrader-based executor is NOT usable;")
        out("executor must be reworked to passorder + get_trade_detail_data version.")
    else:
        out("Neither channel usable: account may be not-logged-in / not-authorized;")
        out("check QMT login state and broker permissions.")
    out("See per-channel lines above. Result file: " + RESULT_FILE)
    out("=========================================================")


def run_probe(ContextInfo=None):
    if _probed["done"]:
        return
    _probed["done"] = True
    try:
        open(RESULT_FILE, "w", encoding="utf-8").close()  # clear old result
    except Exception:
        pass
    account = _resolve_account()
    out("###### QMT authorization probe start account=%s time=%s ######"
        % (account, datetime.now()))
    vba = probe_vba(account, ContextInfo)
    xtt = probe_xttrader(account)
    _final_verdict(vba, xtt)


# ---- Model-trading entry (with ContextInfo, most accurate passorder check) ----
def init(ContextInfo):
    run_probe(ContextInfo)


def handlebar(ContextInfo):
    run_probe(ContextInfo)


# ---- Timed-run / direct-exec entry (top level) ----
try:
    run_probe(None)
except Exception as _e:
    out("top-level probe error: %s" % _e)
