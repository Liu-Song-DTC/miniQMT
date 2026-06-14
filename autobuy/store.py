"""
miniqmt_autobuy 自有存储 (data/autobuy.db)。

两张表:
  buy_history  — 每次买入尝试记录，用于防重(dedup_window_days)与资金/成交复盘
  decision_log — 每轮每只的条件检查明细，复盘"为什么买/没买"
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(MODULE_DIR)
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "data", "autobuy.db")


class AutoBuyStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS buy_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code   TEXT NOT NULL,
                    buy_time     TEXT NOT NULL,
                    run_trigger  TEXT,
                    success      INTEGER NOT NULL DEFAULT 0,
                    http_status  INTEGER,
                    order_result TEXT,
                    amount       REAL
                );
                CREATE INDEX IF NOT EXISTS idx_buy_history_code_time
                    ON buy_history (stock_code, buy_time);

                CREATE TABLE IF NOT EXISTS decision_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_time    TEXT NOT NULL,
                    stock_code  TEXT NOT NULL,
                    passed      INTEGER NOT NULL,
                    reason_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_decision_log_time
                    ON decision_log (run_time);
                """
            )
            self.conn.commit()

    # ---- 写入 ----
    def record_decision(self, run_time: str, stock_code: str, passed: bool, reason: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO decision_log (run_time, stock_code, passed, reason_json) VALUES (?, ?, ?, ?)",
                (run_time, stock_code, 1 if passed else 0, json.dumps(reason, ensure_ascii=False)),
            )
            self.conn.commit()

    def record_buy(self, stock_code: str, run_trigger: str, success: bool,
                   http_status=None, order_result=None, amount=None) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO buy_history "
                "(stock_code, buy_time, run_trigger, success, http_status, order_result, amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    stock_code,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    run_trigger,
                    1 if success else 0,
                    http_status,
                    json.dumps(order_result, ensure_ascii=False) if order_result is not None else None,
                    amount,
                ),
            )
            self.conn.commit()

    # ---- 防重查询 ----
    def recently_bought_codes(self, window_days: int) -> set:
        """返回防重窗口内已成功买入的股票代码集合。

        window_days: -1=永久(全部历史), 0=仅当天, N=最近 N 天(含今天)
        """
        with self._lock:
            if window_days < 0:
                rows = self.conn.execute(
                    "SELECT DISTINCT stock_code FROM buy_history WHERE success = 1"
                ).fetchall()
            else:
                # window_days=0 → 今天 00:00 起; N → (今天-N) 00:00 起
                start = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d 00:00:00")
                rows = self.conn.execute(
                    "SELECT DISTINCT stock_code FROM buy_history WHERE success = 1 AND buy_time >= ?",
                    (start,),
                ).fetchall()
            return {r["stock_code"] for r in rows}

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.close()
            except Exception:
                pass
