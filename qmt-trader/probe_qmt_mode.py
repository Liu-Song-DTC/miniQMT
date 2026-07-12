# probe_qmt_mode.py
# Quick test to confirm whether xttrader is importable in BOTH timed-run and
# model-trading modes. Save and create TWO strategies in QMT:
#   (1) Timed-run   (set period 5000ms)
#   (2) Model-trading
# Use the SAME file for both. Check C:\QuantIPC\probe_result.txt after each run.
#
# ASCII-ONLY, no Chinese.

import os
import json
import traceback
from datetime import datetime

RESULT_FILE = r"C:\QuantIPC\probe_result.txt"


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


def lookup_symbol(name):
    g = globals().get(name)
    if g is not None:
        return g
    b = __builtins__
    if isinstance(b, dict):
        return b.get(name)
    return getattr(b, name, None)


def test_imports():
    out("----- xttrader import test -----")

    # form 1: from xtquant.xttrader import XtQuantTrader (what probe+executor use)
    try:
        from xtquant.xttrader import XtQuantTrader  # noqa: F401
        out("  [OK] from xtquant.xttrader import XtQuantTrader")
    except Exception as e:
        out("  [NG] from xtquant.xttrader import XtQuantTrader: %s" % e)

    # form 2: import xtquant.xttrader as xttrader
    try:
        import xtquant.xttrader as xttrader  # noqa: F401
        out("  [OK] import xtquant.xttrader as xttrader")
    except Exception as e:
        out("  [NG] import xtquant.xttrader as xttrader: %s" % e)

    # form 3: __import__
    try:
        m = __import__("xtquant.xttrader", fromlist=["XtQuantTrader"])
        out("  [OK] __import__('xtquant.xttrader', fromlist=['XtQuantTrader']) -> %s" % m)
    except Exception as e:
        out("  [NG] __import__ xtquant.xttrader: %s" % e)

    # form 4: importlib
    try:
        import importlib
        m = importlib.import_module("xtquant.xttrader")
        out("  [OK] importlib.import_module('xtquant.xttrader') -> %s" % m)
    except Exception as e:
        out("  [NG] importlib.import_module: %s" % e)

    # form 5: xttype (also needed)
    try:
        from xtquant.xttype import StockAccount
        out("  [OK] from xtquant.xttype import StockAccount -> %s" % StockAccount)
    except Exception as e:
        out("  [NG] xtquant.xttype: %s" % e)

    # form 6: xtconstant
    try:
        from xtquant import xtconstant
        out("  [OK] from xtquant import xtconstant")
    except Exception as e:
        out("  [NG] from xtquant import xtconstant: %s" % e)

    # form 7: xtdata
    try:
        from xtquant import xtdata
        out("  [OK] from xtquant import xtdata")
    except Exception as e:
        out("  [NG] from xtquant import xtdata: %s" % e)

    # form 8: passorder existence (not import - namespace lookup)
    passorder = lookup_symbol("passorder")
    out("  passorder callable(globals/builtins): %s" % callable(passorder))

    # form 9: get_trade_detail_data
    gtdd = lookup_symbol("get_trade_detail_data")
    out("  get_trade_detail_data callable(globals/builtins): %s" % callable(gtdd))


_done = False


def run():
    global _done
    if _done:
        return
    _done = True
    try:
        open(RESULT_FILE, "w", encoding="utf-8").close()
    except Exception:
        pass
    out("###### QMT mode import probe ######")
    test_imports()
    out("###### done ######")


# ---- Both modes ----
def init(ContextInfo):
    run()


def handlebar(ContextInfo):
    run()


# Top-level (timed-run)
try:
    run()
except Exception as _e:
    out("top-level error: %s\n%s" % (_e, traceback.format_exc()))
