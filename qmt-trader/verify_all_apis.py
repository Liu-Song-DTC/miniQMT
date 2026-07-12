###############################################################################
# verify_all_apis.py
# Big-QMT API verification: test every xttrader method AND VBA method that
# the executor uses, so we know once and for all which calls work.
#
# ASCII-ONLY. READ-ONLY. Dump results into C:\QuantIPC\api_verify_result.txt
###############################################################################

import os, json, sys, time, traceback
from datetime import datetime

RESULT_FILE = r"C:\QuantIPC\api_verify_result.txt"


def out(msg):
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


def _vba(name):
    g = globals().get(name)
    if g is not None:
        return g
    b = __builtins__
    if isinstance(b, dict):
        return b.get(name)
    return getattr(b, name, None)


def main():
    try:
        open(RESULT_FILE, "w", encoding="utf-8").close()
    except Exception:
        pass

    out("===== API verify start =====")

    # 1. read account_config
    account_id = "YOUR_ACCOUNT"
    cfg_paths = []
    ipc_root = r"C:\QuantIPC"
    try:
        for name in sorted(os.listdir(ipc_root)):
            cp = os.path.join(ipc_root, name, "config.json")
            if os.path.exists(cp):
                cfg_paths.append(cp)
    except Exception:
        pass
    qt_path = r"C:\QMT\userdata_mini"
    for cp in cfg_paths:
        if os.path.exists(cp):
            try:
                with open(cp, encoding="utf-8") as f:
                    j = json.load(f)
                account_id = j.get("account_id", account_id)
                qt_path = j.get("qmt_path", qt_path)
                break
            except Exception:
                pass

    out("account_id=%s  qmt_path=%s" % (account_id, qt_path))

    # 2. check VBA builtins
    out("--- VBA builtins ---")
    for name in ("passorder", "cancel", "get_trade_detail_data"):
        fn = _vba(name)
        out("  %s callable: %s" % (name, callable(fn)))
        if name == "get_trade_detail_data" and callable(fn):
            for args in [(account_id, "STOCK", "ACCOUNT"),
                         (account_id, "stock", "account"),
                         (account_id, "ACCOUNT")]:
                try:
                    data = fn(*args)
                    if data:
                        o = data[0]
                        out("  VBA account query ok args=%s: total=%s avail=%s"
                            % (args,
                               getattr(o, "m_dTotalAsset", getattr(o, "m_dBalance", "?")),
                               getattr(o, "m_dAvailable", "?")))
                        break
                except Exception as e:
                    out("  VBA account args=%s error: %s" % (args, str(e)[:80]))
            for args in [(account_id, "STOCK", "POSITION"), (account_id, "POSITION")]:
                try:
                    pos = fn(*args)
                    out("  VBA positions query ok args=%s: count=%s" % (args, len(pos) if pos else 0))
                    if pos:
                        p0 = pos[0]
                        out("  first pos: %s vol=%s avail=%s open=%s last=%s mv=%s"
                            % (getattr(p0, "m_strInstrumentID", "?"),
                               getattr(p0, "m_nVolume", "?"),
                               getattr(p0, "m_nCanUseVolume", "?"),
                               getattr(p0, "m_dOpenPrice", "?"),
                               getattr(p0, "m_dLastPrice", "?"),
                               getattr(p0, "m_dMarketValue", "?")))
                    break
                except Exception as e:
                    out("  VBA positions args=%s error: %s" % (args, str(e)[:80]))

    # 3. check xttrader
    out("--- xttrader ---")
    XtQuantTrader = None
    try:
        _xt = __import__("xtquant.xttrader", fromlist=["XtQuantTrader"])
        XtQuantTrader = _xt.XtQuantTrader
        out("  import ok: %s" % XtQuantTrader)
    except Exception as e:
        out("  import failed: %s" % e)

    if XtQuantTrader is not None:
        xt = None
        try:
            xt = XtQuantTrader(qt_path, int(time.time()) % 100000)
            out("  init ok: %s" % xt)

            rc = xt.connect()
            out("  connect() rc=%s" % rc)

            if hasattr(xt, "login"):
                out("  .login exists")
                try:
                    xt.login(account_id)
                    out("  login() ok")
                except Exception as e:
                    out("  login() error: %s" % e)
            else:
                out("  .login DOES NOT EXIST")

            for method in ("query_account", "query_stock_positions",
                           "query_stock_asset", "query_all_orders",
                           "order_stock", "cancel_order"):
                out("  .%s exists: %s" % (method, hasattr(xt, method)))

            if hasattr(xt, "query_account"):
                try:
                    acct = xt.query_account(account_id)
                    out("  query_account ok: total=%s avail=%s mv=%s"
                        % (getattr(acct, "total_asset", "?"),
                           getattr(acct, "available", getattr(acct, "cash", "?")),
                           getattr(acct, "market_value", "?")))
                except Exception as e:
                    out("  query_account error: %s" % e)
            else:
                out("  query_account NOT AVAILABLE -- MUST use VBA path")

            if hasattr(xt, "query_stock_positions"):
                try:
                    pos = xt.query_stock_positions(account_id)
                    out("  query_stock_positions ok: count=%s" % (len(pos) if pos else 0))
                    if pos:
                        p0 = pos[0]
                        out("  first pos: %s vol=%s avail=%s cost=%s mp=%s"
                            % (getattr(p0, "stock_code", "?"),
                               getattr(p0, "volume", "?"),
                               getattr(p0, "can_use_volume", "?"),
                               getattr(p0, "open_price", "?"),
                               getattr(p0, "market_price", "?")))
                except Exception as e:
                    out("  query_stock_positions error: %s" % e)
            else:
                out("  query_stock_positions NOT AVAILABLE -- MUST use VBA path")

            if hasattr(xt, "query_all_orders"):
                try:
                    orders = xt.query_all_orders(account_id)
                    out("  query_all_orders ok: count=%s" % (len(orders) if orders else 0))
                except Exception as e:
                    out("  query_all_orders error: %s" % e)
            else:
                out("  query_all_orders NOT AVAILABLE")

        except Exception as e:
            out("  xttrader error: %s\n%s" % (e, traceback.format_exc()))
        finally:
            try:
                if xt is not None and hasattr(xt, "stop"):
                    xt.stop()
            except Exception:
                pass

    out("===== API verify done =====")


# ---- entry ----
def init(ContextInfo):
    main()


def handlebar(ContextInfo):
    main()


try:
    main()
except Exception as _e:
    out("top-level error: %s\n%s" % (_e, traceback.format_exc()))
