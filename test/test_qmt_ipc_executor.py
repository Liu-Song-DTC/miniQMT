"""
qmt_trade_executor.py tests -- compact rewrite aligned with current module.
"""
import os, sys, json, time, types, shutil, tempfile, unittest, threading
from contextlib import contextmanager

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "qmt-trader"))

_MODULE_TMP = tempfile.mkdtemp(prefix="ipc_exec_module_")
os.environ["QMT_IPC_ROOT"] = _MODULE_TMP

import qmt_trade_executor as ex
ex.DIR_LOG = os.path.join(_MODULE_TMP, "qmt_log")
os.makedirs(ex.DIR_LOG, exist_ok=True)

def tearDownModule():
    shutil.rmtree(_MODULE_TMP, ignore_errors=True)

class FakeOrder:
    def __init__(self, oid, status, price=10.48, vol=1000):
        self.order_id = oid; self.order_status = status
        self.traded_price = price; self.traded_vol = vol

class FakeTrader:
    def __init__(self, fill_status=56, seq=8888):
        self.fill_status = fill_status; self.seq = seq
        self.cancel_called = []; self.orders_placed = []
    def connect(self): pass
    def order_stock(self, aid, sc, act, vol, pt, price, *ex):
        self.orders_placed.append((aid, sc, act, vol, price)); return self.seq
    def query_all_orders(self, aid):
        return [FakeOrder(self.seq, self.fill_status)]
    def cancel_order(self, aid, seq): self.cancel_called.append(seq)

class _ExecBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ipc_exec_")
        self.acc_dir = os.path.join(self.tmp, "TEST_ACC_1")
        self.acc = {"account_id":"TEST_ACC_1","qmt_path":"C:/QMT/userdata_mini",
                    "dir":self.acc_dir,"dirs":ex._account_dirs(self.acc_dir)}
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    def _write_pending(self, oid, action="buy", stock="000001.SZ",
                       volume=1000, price=10.5, price_type="limit", timeout_sec=2):
        order = dict(version="1.0", order_id=oid, timestamp="2026-07-11 10:00:00.000",
                     action=action, stock_code=stock, price_type=price_type, price=price,
                     volume=volume, strategy="test", timeout_sec=timeout_sec, remark="")
        path = os.path.join(self.acc["dirs"]["pending"], "ord_%s.json" % oid)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(order, f, ensure_ascii=False)
        return path

# ---- atomic write ----
class TestAtomicWrite(_ExecBase):
    def test_roundtrip_no_tmp(self):
        p = os.path.join(self.tmp, "x.json")
        ex._atomic_write_json(p, {"a":1,"b":"hello"})
        self.assertEqual(json.load(open(p, encoding="utf-8")), {"a":1,"b":"hello"})
        self.assertEqual([f for f in os.listdir(self.tmp) if f.endswith(".tmp")], [])
    def test_overwrite(self):
        p = os.path.join(self.tmp, "x.json")
        ex._atomic_write_json(p, {"v":1}); ex._atomic_write_json(p, {"v":2})
        self.assertEqual(json.load(open(p, encoding="utf-8"))["v"], 2)

# ---- write_done ----
class TestWriteDone(_ExecBase):
    def test_done_and_cleanup(self):
        pr = os.path.join(self.acc["dirs"]["processing"], "ord_100.json")
        with open(pr, "w", encoding="utf-8") as f:
            json.dump({"order_id":100,"volume":1000,"action":"buy","stock_code":"000001.SZ"}, f)
        ex.write_done(self.acc["dirs"], pr,
                      {"order_id":100,"volume":1000,"action":"buy","stock_code":"000001.SZ"},
                      "filled", "ok", filled_price=10.5, filled_vol=1000)
        self.assertTrue(os.path.exists(os.path.join(self.acc["dirs"]["done"],"ord_100.json")))
        self.assertFalse(os.path.exists(pr))
    def test_error_field(self):
        pr = os.path.join(self.acc["dirs"]["processing"], "ord_101.json")
        ex.write_done(self.acc["dirs"], pr,
                      {"order_id":101,"volume":1000,"action":"buy","stock_code":"000001.SZ"},
                      "rejected", "no cash")
        rec = json.load(open(os.path.join(self.acc["dirs"]["done"],"ord_101.json"), encoding="utf-8"))
        self.assertEqual(rec["status"], "rejected"); self.assertEqual(rec["error"], "no cash")

# ---- discover_accounts ----
class TestDiscoverAccounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ipc_disc_")
        self._r, self._f = ex.IPC_ROOT, ex.ACCOUNT_FILTER
        ex.IPC_ROOT = self.tmp; ex.ACCOUNT_FILTER = ""
    def tearDown(self):
        ex.IPC_ROOT = self._r; ex.ACCOUNT_FILTER = self._f
        shutil.rmtree(self.tmp, ignore_errors=True)
    def _mk(self, aid, qp):
        d = os.path.join(self.tmp, aid); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"account_id": aid, "qmt_path": qp}, f)
    def test_multi(self):
        self._mk("A1","C:/"); self._mk("A2","C:/")
        self.assertEqual(sorted(a["account_id"] for a in ex.discover_accounts()), ["A1","A2"])
    def test_skip_no_config(self):
        os.makedirs(os.path.join(self.tmp, "no_cfg"), exist_ok=True)
        self._mk("A1","C:/")
        self.assertEqual([a["account_id"] for a in ex.discover_accounts()], ["A1"])
    def test_filter(self):
        self._mk("A1","C:/"); self._mk("A2","C:/"); ex.ACCOUNT_FILTER = "A2"
        self.assertEqual([a["account_id"] for a in ex.discover_accounts()], ["A2"])
    def test_legacy_flat(self):
        os.makedirs(os.path.join(self.tmp, "orders"), exist_ok=True)
        accs = ex.discover_accounts()
        self.assertEqual(len(accs), 1); self.assertEqual(accs[0]["dir"], self.tmp)

# ---- leftovers ----
class TestRecoverLeftovers(_ExecBase):
    def test_stale(self):
        pr = os.path.join(self.acc["dirs"]["processing"], "ord_200.json")
        with open(pr, "w", encoding="utf-8") as f:
            json.dump({"order_id":200,"volume":1000}, f)
        os.utime(pr, (time.time()-(ex.PROCESSING_STALE_SEC+10),)*2)
        ex.recover_leftovers(self.acc)
        self.assertFalse(os.path.exists(pr))
        d = os.path.join(self.acc["dirs"]["done"], "ord_200.json")
        self.assertTrue(os.path.exists(d))
        self.assertEqual(json.load(open(d, encoding="utf-8"))["status"], "error")
    def test_fresh_untouched(self):
        pr = os.path.join(self.acc["dirs"]["processing"], "ord_201.json")
        with open(pr, "w", encoding="utf-8") as f:
            json.dump({"order_id":201,"volume":1000}, f)
        ex.recover_leftovers(self.acc)
        self.assertTrue(os.path.exists(pr))
    def test_no_resubmit(self):
        pr = os.path.join(self.acc["dirs"]["processing"], "ord_202.json")
        with open(pr, "w", encoding="utf-8") as f:
            json.dump({"order_id":202,"volume":1000}, f)
        os.utime(pr, (time.time()-(ex.PROCESSING_STALE_SEC+10),)*2)
        ex.recover_leftovers(self.acc)
        self.assertEqual([f for f in os.listdir(self.acc["dirs"]["pending"]) if f.endswith(".json")], [])

# ---- archive ----
class TestArchiveOldDone(_ExecBase):
    def test_moved(self):
        od = os.path.join(self.acc["dirs"]["done"], "ord_1.json")
        nd = os.path.join(self.acc["dirs"]["done"], "ord_2.json")
        for p in (od, nd):
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"order_id": os.path.basename(p)}, f)
        os.utime(od, (time.time()-(ex.DONE_RETENTION_SEC+100),)*2)
        ex.archive_old(self.acc)
        self.assertFalse(os.path.exists(od)); self.assertTrue(os.path.exists(nd))
        self.assertTrue(os.path.exists(os.path.join(self.acc["dir"],"orders","done_archive","ord_1.json")))

# ---- process_one_order ----
class TestProcessOrderFlow(_ExecBase):
    def test_buy_filled(self):
        path = self._write_pending(300, action="buy")
        fake = FakeTrader(fill_status=56, seq=8888)
        _orig_connect = ex._try_connect_xttrader
        ex._try_connect_xttrader = lambda qp: fake
        try:
            ex.process_one_order(self.acc, path)
        finally:
            ex._try_connect_xttrader = _orig_connect
        rec = json.load(open(os.path.join(self.acc["dirs"]["done"],"ord_300.json"), encoding="utf-8"))
        self.assertEqual(rec["status"], "filled")
        placed_account = fake.orders_placed[0][0]
        self.assertEqual(getattr(placed_account, "account_id", placed_account), "TEST_ACC_1")

    def test_timeout(self):
        path = self._write_pending(301, action="buy", timeout_sec=1)
        fake = FakeTrader(fill_status=48, seq=9001)
        _o = ex._try_connect_xttrader; ex._try_connect_xttrader = lambda qp: fake
        try: ex.process_one_order(self.acc, path)
        finally: ex._try_connect_xttrader = _o
        rec = json.load(open(os.path.join(self.acc["dirs"]["done"],"ord_301.json"), encoding="utf-8"))
        self.assertEqual(rec["status"], "cancelled_timeout")
        self.assertIn(9001, fake.cancel_called)

    def test_midflight_cancel(self):
        path = self._write_pending(302, action="buy", timeout_sec=3)
        cp = os.path.join(self.acc["dirs"]["cancel"], "cancel_302.json")
        def delayed():
            time.sleep(0.7)
            with open(cp, "w", encoding="utf-8") as f:
                json.dump({"order_id": 302}, f)
        threading.Thread(target=delayed, daemon=True).start()
        fake = FakeTrader(fill_status=48, seq=9100)
        _o = ex._try_connect_xttrader; ex._try_connect_xttrader = lambda qp: fake
        try: ex.process_one_order(self.acc, path)
        finally: ex._try_connect_xttrader = _o
        self.assertIn(9100, fake.cancel_called)
        self.assertFalse(os.path.exists(cp))

    def test_cancel_before_submit(self):
        path = self._write_pending(303, action="buy")
        cp = os.path.join(self.acc["dirs"]["cancel"], "cancel_303.json")
        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"order_id": 303}, f)
        fake = FakeTrader(fill_status=56, seq=9200)
        _o = ex._try_connect_xttrader; ex._try_connect_xttrader = lambda qp: fake
        try: ex.process_one_order(self.acc, path)
        finally: ex._try_connect_xttrader = _o
        rec = json.load(open(os.path.join(self.acc["dirs"]["done"],"ord_303.json"), encoding="utf-8"))
        self.assertEqual(rec["status"], "cancelled")
        self.assertEqual(fake.orders_placed, [])

# ---- handle_account heartbeat ----
class TestHandleAccountHeartbeat(_ExecBase):
    def test_heartbeat(self):
        ex.handle_account(self.acc)
        hb = os.path.join(self.acc["dirs"]["status"], "heartbeat.json")
        self.assertTrue(os.path.exists(hb))
        self.assertEqual(json.load(open(hb, encoding="utf-8"))["account_id"], "TEST_ACC_1")
        self.assertEqual([f for f in os.listdir(self.acc["dirs"]["status"]) if f.endswith(".tmp")], [])

if __name__ == "__main__":
    unittest.main()
