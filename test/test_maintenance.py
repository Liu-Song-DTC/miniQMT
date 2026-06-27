import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

import config
from autobuy.store import AutoBuyStore
from maintenance import cleanup_autobuy_db, cleanup_trading_db, rotate_plain_log, run_database_maintenance


class TestMaintenance(unittest.TestCase):
    def test_run_database_maintenance_logs_compact_info(self):
        result = {
            "trading_db": {
                "db_path": "data/trading.db",
                "trade_records": 1,
                "grid_sessions": 2,
                "premarket_sync_history": 0,
                "config_history": 0,
                "vacuum": False,
            },
            "autobuy_db": {
                "db_path": "data/autobuy.db",
                "decision_log": 3,
                "vacuum": True,
            },
        }

        with patch("maintenance.cleanup_trading_db", return_value=result["trading_db"]), \
             patch("maintenance.cleanup_autobuy_db", return_value=result["autobuy_db"]), \
             patch("maintenance.logger") as mock_logger:
            self.assertEqual(run_database_maintenance(datetime(2026, 6, 27, 0, 10, 0)), result)

        mock_logger.info.assert_called_once_with("数据库维护完成: 清理 6 行, VACUUM=已执行")
        mock_logger.debug.assert_called_once_with(f"数据库维护明细: {result}")

    def test_rotate_plain_log_keeps_limited_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "xqm_manager.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("current-log")
            with open(log_path + ".1", "w", encoding="utf-8") as f:
                f.write("backup-1")
            with open(log_path + ".2", "w", encoding="utf-8") as f:
                f.write("backup-2")
            with open(log_path + ".3", "w", encoding="utf-8") as f:
                f.write("backup-3")

            rotated = rotate_plain_log(log_path, max_bytes=5, backup_count=3)

            self.assertTrue(rotated)
            self.assertTrue(os.path.exists(log_path))
            self.assertEqual(os.path.getsize(log_path), 0)
            with open(log_path + ".1", "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "current-log")
            with open(log_path + ".2", "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "backup-1")
            with open(log_path + ".3", "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "backup-2")

    def test_cleanup_autobuy_decision_log_only(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = AutoBuyStore(db_path)
        self.addCleanup(lambda: (store.close(), os.path.exists(db_path) and os.remove(db_path)))

        store.record_decision("2026-01-01 10:00:00", "600000.SH", False, {"failed": ["old"]})
        store.record_decision("2026-06-26 10:00:00", "000001.SZ", True, {"failed": []})
        store.conn.execute(
            """
            INSERT INTO buy_history
            (stock_code, buy_time, run_trigger, success)
            VALUES (?, ?, ?, ?)
            """,
            ("600000.SH", "2026-01-01 10:00:00", "test", 1),
        )
        store.conn.commit()

        with patch.object(config, "AUTOBUY_DECISION_LOG_RETENTION_DAYS", 90), \
             patch.object(config, "DB_MAINTENANCE_ENABLE_VACUUM", False):
            summary = cleanup_autobuy_db(db_path, now=datetime(2026, 6, 27, 0, 10, 0))

        self.assertEqual(summary["decision_log"], 1)
        rows = store.conn.execute("SELECT stock_code FROM decision_log ORDER BY id").fetchall()
        self.assertEqual([row["stock_code"] for row in rows], ["000001.SZ"])
        buy_rows = store.conn.execute("SELECT stock_code FROM buy_history").fetchall()
        self.assertEqual([row["stock_code"] for row in buy_rows], ["600000.SH"])

    def test_cleanup_trading_db_keeps_active_grid_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "trading.db")
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(
                """
                CREATE TABLE trade_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_time TEXT
                );
                CREATE TABLE premarket_sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_time TEXT
                );
                CREATE TABLE config_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    changed_at TEXT
                );
                CREATE TABLE grid_trading_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT,
                    stop_time TEXT,
                    updated_at TEXT,
                    created_at TEXT
                );
                CREATE TABLE grid_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES grid_trading_sessions(id) ON DELETE CASCADE
                );
                """
            )
            conn.executemany(
                "INSERT INTO trade_records (trade_time) VALUES (?)",
                [("2022-01-01 10:00:00",), ("2026-06-26 10:00:00",)],
            )
            conn.executemany(
                "INSERT INTO premarket_sync_history (sync_time) VALUES (?)",
                [("2024-01-01 09:25:00",), ("2026-06-26 09:25:00",)],
            )
            conn.executemany(
                "INSERT INTO config_history (changed_at) VALUES (?)",
                [("2024-01-01 10:00:00",), ("2026-06-26 10:00:00",)],
            )
            conn.executemany(
                """
                INSERT INTO grid_trading_sessions
                (id, status, stop_time, updated_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (1, "active", None, "2024-01-01 10:00:00", "2024-01-01 10:00:00"),
                    (2, "stopped", "2024-01-01 10:00:00", "2024-01-01 10:00:00", "2024-01-01 10:00:00"),
                    (3, "stopped", "2026-06-26 10:00:00", "2026-06-26 10:00:00", "2026-06-26 10:00:00"),
                ],
            )
            conn.executemany(
                "INSERT INTO grid_trades (session_id) VALUES (?)",
                [(1,), (2,), (3,)],
            )
            conn.commit()
            conn.close()

            with patch.object(config, "DB_MAINTENANCE_ENABLE_VACUUM", False):
                summary = cleanup_trading_db(db_path, now=datetime(2026, 6, 27, 0, 10, 0))

            conn = sqlite3.connect(db_path)
            try:
                self.assertEqual(summary["trade_records"], 1)
                self.assertEqual(summary["premarket_sync_history"], 1)
                self.assertEqual(summary["config_history"], 1)
                self.assertEqual(summary["grid_sessions"], 1)
                sessions = conn.execute("SELECT id FROM grid_trading_sessions ORDER BY id").fetchall()
                self.assertEqual([row[0] for row in sessions], [1, 3])
                trades = conn.execute("SELECT session_id FROM grid_trades ORDER BY session_id").fetchall()
                self.assertEqual([row[0] for row in trades], [1, 3])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
