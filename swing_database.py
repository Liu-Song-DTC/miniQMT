"""
盘中高抛低吸策略 - 数据持久化模块
管理摆动交易会话和成交记录的 SQLite 存储
"""
import sqlite3
import os
import json
from datetime import datetime
from logger import get_logger

logger = get_logger("swing_database")


class SwingDatabase:
    """摆动交易数据库管理"""

    def __init__(self, db_path=None):
        if db_path is None:
            import config
            data_dir = getattr(config, 'DATA_DIR', 'data')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "swing_trading.db")
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_tables()

    def init_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS swing_sessions (
                stock_code TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                base_volume_start INTEGER DEFAULT 0,
                total_buy_volume INTEGER DEFAULT 0,
                total_sell_volume INTEGER DEFAULT 0,
                buy_count INTEGER DEFAULT 0,
                sell_count INTEGER DEFAULT 0,
                total_profit REAL DEFAULT 0.0,
                max_profit REAL DEFAULT 0.0,
                consecutive_failures INTEGER DEFAULT 0,
                last_buy_time TEXT,
                last_sell_time TEXT,
                last_update TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS swing_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                direction TEXT NOT NULL,
                price REAL NOT NULL,
                volume INTEGER NOT NULL,
                amount REAL NOT NULL,
                confidence INTEGER NOT NULL,
                signal_detail TEXT,
                order_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_swing_trades_stock_date
            ON swing_trades(stock_code, date)
        ''')
        self.conn.commit()

    def save_session(self, session_data):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO swing_sessions (
                stock_code, date, enabled, base_volume_start,
                total_buy_volume, total_sell_volume, buy_count, sell_count,
                total_profit, max_profit, consecutive_failures,
                last_buy_time, last_sell_time, last_update
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_data.get('stock_code', ''),
            session_data.get('date', datetime.now().strftime('%Y-%m-%d')),
            int(session_data.get('enabled', 1)),
            session_data.get('base_volume_start', 0),
            session_data.get('total_buy_volume', 0),
            session_data.get('total_sell_volume', 0),
            session_data.get('buy_count', 0),
            session_data.get('sell_count', 0),
            session_data.get('total_profit', 0.0),
            session_data.get('max_profit', 0.0),
            session_data.get('consecutive_failures', 0),
            session_data.get('last_buy_time', ''),
            session_data.get('last_sell_time', ''),
            datetime.now().isoformat(),
        ))
        self.conn.commit()

    def load_session(self, stock_code):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM swing_sessions WHERE stock_code=?",
            (stock_code,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def load_all_active_sessions(self):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT * FROM swing_sessions WHERE date=? AND enabled=1",
            (today,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def save_trade(self, trade_record):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO swing_trades (
                stock_code, date, time, direction, price,
                volume, amount, confidence, signal_detail, order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_record.get('stock_code', ''),
            trade_record.get('date', datetime.now().strftime('%Y-%m-%d')),
            trade_record.get('time', datetime.now().strftime('%H:%M:%S')),
            trade_record.get('direction', ''),
            trade_record.get('price', 0.0),
            trade_record.get('volume', 0),
            trade_record.get('amount', 0.0),
            trade_record.get('confidence', 0),
            trade_record.get('signal_detail', ''),
            trade_record.get('order_id', ''),
        ))
        self.conn.commit()

    def get_today_trades(self, stock_code=None):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        if stock_code:
            cursor.execute(
                "SELECT * FROM swing_trades WHERE stock_code=? AND date=? ORDER BY id DESC",
                (stock_code, today)
            )
        else:
            cursor.execute(
                "SELECT * FROM swing_trades WHERE date=? ORDER BY id DESC",
                (today,)
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_recent_trades(self, stock_code=None, days=5):
        cursor = self.conn.cursor()
        if stock_code:
            cursor.execute(
                "SELECT * FROM swing_trades WHERE stock_code=? ORDER BY id DESC LIMIT ?",
                (stock_code, days * 10)
            )
        else:
            cursor.execute(
                "SELECT * FROM swing_trades ORDER BY id DESC LIMIT ?",
                (days * 20,)
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_today_summary(self, stock_code):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT
                direction,
                COUNT(*) as cnt,
                SUM(volume) as total_volume,
                SUM(amount) as total_amount,
                AVG(price) as avg_price
            FROM swing_trades
            WHERE stock_code=? AND date=?
            GROUP BY direction
        ''', (stock_code, today))
        rows = cursor.fetchall()
        summary = {'buy': {}, 'sell': {}}
        for row in rows:
            d = dict(row)
            direction = d.pop('direction')
            summary[direction] = d
        return summary

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
