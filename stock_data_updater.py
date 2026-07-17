#!/usr/bin/env python3
"""
盘后全市场日线数据增量更新器

用法:
  python stock_data_updater.py                     # 增量更新全部股票
  python stock_data_updater.py --stock 000001.SZ   # 更新单只
  python stock_data_updater.py --since 2026-07-01  # 从指定日期补数据
  python stock_data_updater.py --check             # 检查数据状态
  python stock_data_updater.py --failed            # 重试上次失败的股票

数据格式: backtrader CSV (datetime,open,high,low,close,volume,openinterest,
          amount,amplitude,change_percent,change_amount,turnover_rate)
"""
import os
import sys
import csv
import json
import time
import argparse
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Set

import numpy as np
import pandas as pd

from logger import get_logger

logger = get_logger("stock_updater")


class StockDataUpdater:
    """盘后全市场日线数据增量更新器"""

    def __init__(self, data_dir=None):
        import config
        if data_dir is None:
            data_dir = getattr(config, 'STOCK_DATA_DIR', r'D:\quant\data')
        self.data_dir = Path(data_dir)
        self.csv_dir = self.data_dir / "stock_data" / "backtrader_data"
        self.meta_file = self.data_dir / "stock_data" / "metadata.json"
        self.failed_file = self.data_dir / "stock_data" / "failed_stocks.json"

        self.csv_dir.mkdir(parents=True, exist_ok=True)

        self.xtdata = None
        self.mootdx_client = None

        # 统计
        self.stats = {'updated': 0, 'skipped': 0, 'failed': 0, 'new': 0, 'empty': 0}
        self.failed_stocks: List[str] = []
        self._first_error_logged = False

    # ==================== 股票列表 ====================

    def get_stock_list(self) -> List[str]:
        """从现有CSV文件获取股票列表"""
        stocks = []
        try:
            if self.csv_dir.exists():
                for f in self.csv_dir.glob("*_qfq.csv"):
                    code = f.stem.replace("_qfq", "")
                    if code and not code.startswith('.'):
                        stocks.append(code)
        except OSError:
            logger.warning(f"无法读取CSV目录: {self.csv_dir}")
        if not stocks:
            logger.warning(f"未找到已有CSV文件({self.csv_dir})，将使用默认股票池")
            import config
            stocks = [s.split('.')[0] for s in getattr(config, 'STOCK_POOL', [])]
        return sorted(stocks)

    def _code_to_csv_path(self, stock_code: str) -> Path:
        return self.csv_dir / f"{stock_code}_qfq.csv"

    # ==================== CSV读写 ====================

    CSV_FIELDS = ['datetime', 'open', 'high', 'low', 'close', 'volume',
                  'openinterest', 'amount', 'amplitude', 'change_percent',
                  'change_amount', 'turnover_rate']

    def read_last_date(self, stock_code: str) -> Optional[str]:
        """读取CSV最后一行的日期，校验格式后返回 YYYY-MM-DD 或 None"""
        csv_path = self._code_to_csv_path(stock_code)
        try:
            if not csv_path.exists():
                return None
        except OSError:
            return None
        try:
            df = pd.read_csv(csv_path)
            if df.empty or 'datetime' not in df.columns:
                return None
            last = str(df['datetime'].iloc[-1]).strip()
            return last if self._is_valid_date(last) else None
        except Exception:
            try:
                with open(csv_path, 'r') as f:
                    lines = f.readlines()
                    if len(lines) < 2:
                        return None
                    last_line = lines[-1].strip()
                    val = last_line.split(',')[0] if last_line else ''
                    return val if self._is_valid_date(val) else None
            except Exception:
                return None

    @staticmethod
    def _is_valid_date(val: str) -> bool:
        """校验是否为 YYYY-MM-DD 格式的合法日期"""
        if not val or len(val) != 10 or val[4] != '-' or val[7] != '-':
            return False
        try:
            datetime.strptime(val, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def append_to_csv(self, stock_code: str, new_rows: list):
        """追加新数据行到CSV文件"""
        csv_path = self._code_to_csv_path(stock_code)
        try:
            file_exists = csv_path.exists()
        except OSError:
            file_exists = False

        try:
            with open(csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(self.CSV_FIELDS)
                for row in new_rows:
                    writer.writerow(row)
        except OSError as e:
            logger.error(f"写入 {stock_code} CSV失败: {str(e)[:80]}")
            raise

    # ==================== 数据源: xtdata ====================

    def _init_xtdata(self) -> bool:
        if self.xtdata is not None:
            return True
        try:
            import xtquant.xtdata as xt
            self.xtdata = xt
            try:
                xt.connect()
            except Exception:
                pass
            return True
        except ImportError:
            logger.warning("xtquant.xtdata 不可用，将尝试 mootdx 降级")
            return False

    def _xt_code(self, stock_code: str) -> str:
        """转换为 xtdata 标准代码格式"""
        if '.' not in stock_code:
            return f"{stock_code}.{'SH' if stock_code.startswith(('6','9','5')) else 'SZ'}"
        return stock_code

    def _download_via_xtdata(self, stock_code: str, since_date: str):
        """下载并返回日线数据。返回 (status, df)"""
        if not self._init_xtdata():
            return 'error', None

        try:
            xt_code = self._xt_code(stock_code)
            start = since_date.replace('-', '')

            # 先下载到本地缓存
            self.xtdata.download_history_data(
                xt_code, period='1d',
                start_time=start, end_time='',
                incrementally=True,
            )

            data = self.xtdata.get_market_data(
                field_list=['open', 'high', 'low', 'close', 'volume', 'amount', 'preClose'],
                stock_list=[xt_code],
                period='1d',
                start_time=since_date.replace('-', ''),
                dividend_type='front',
                fill_data=False,
            )

            if data is None or data['close'].empty or data['close'].shape[0] == 0:
                return 'empty', None

            closes = data['close'].iloc[:, 0]
            opens = data['open'].iloc[:, 0]
            highs = data['high'].iloc[:, 0]
            lows = data['low'].iloc[:, 0]
            volumes = data['volume'].iloc[:, 0]
            amounts = data.get('amount', data['volume']).iloc[:, 0]

            if 'preClose' in data:
                precloses = data['preClose'].iloc[:, 0]
            else:
                precloses = closes.shift(1).fillna(closes.iloc[0])

            dates = [str(d).strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d).split(' ')[0]
                     for d in closes.index]

            n = len(closes)
            rows = []
            for i in range(n):
                dt = dates[i]
                if dt < since_date:
                    continue

                o = float(opens.iloc[i])
                h = float(highs.iloc[i])
                l = float(lows.iloc[i])
                c = float(closes.iloc[i])
                v = float(volumes.iloc[i])
                a = float(amounts.iloc[i])
                pc = float(precloses.iloc[i]) if precloses is not None and i < n else c

                pct_chg = ((c - pc) / pc * 100) if pc > 0 else 0
                chg = c - pc
                ampl = ((h - l) / pc * 100) if pc > 0 else 0

                rows.append({
                    'datetime': dt,
                    'open': round(o, 2), 'high': round(h, 2),
                    'low': round(l, 2), 'close': round(c, 2),
                    'volume': int(v), 'openinterest': 0,
                    'amount': round(a, 2), 'amplitude': round(ampl, 2),
                    'change_percent': round(pct_chg, 2),
                    'change_amount': round(chg, 2), 'turnover_rate': 0,
                })

            return ('ok', pd.DataFrame(rows)) if rows else ('empty', None)

        except Exception as e:
            if not self._first_error_logged:
                logger.error(f"[xtdata] {stock_code} 下载异常: {str(e)[:100]}")
                self._first_error_logged = True
            return 'error', None

    # ==================== 数据源: mootdx ====================

    def _init_mootdx(self) -> bool:
        if self.mootdx_client is not None:
            return True
        try:
            from mootdx.quotes import Quotes
            self.mootdx_client = Quotes.factory('std')
            return True
        except Exception:
            logger.debug("mootdx 不可用")
            return False

    def _download_via_mootdx(self, stock_code: str, since_date: str):
        """通过 mootdx(通达信) 下载日线数据。返回 (status, df)"""
        if not self._init_mootdx():
            return 'error', None

        try:
            clean_code = stock_code.split('.')[0] if '.' in stock_code else stock_code
            market = 1 if clean_code.startswith(('6', '9', '5')) else 0

            df = self.mootdx_client.bars(
                symbol=clean_code, frequency=9, offset=300, market=market,
            )

            if df is None or df.empty:
                return 'empty', None

            df = df.rename(columns={'datetime': 'datetime_raw'})
            if 'datetime_raw' not in df.columns:
                return 'empty', None

            df['datetime'] = pd.to_datetime(df['datetime_raw']).dt.strftime('%Y-%m-%d')
            df = df[df['datetime'] >= since_date].copy()
            if df.empty:
                return 'empty', None

            rows = []
            prev_close = None
            for _, row in df.iterrows():
                o = float(row['open']); h = float(row['high'])
                l = float(row['low']); c = float(row['close'])
                v = float(row.get('volume', 0)); a = float(row.get('amount', 0))

                pc = prev_close if prev_close is not None else o
                prev_close = c

                pct_chg = ((c - pc) / pc * 100) if pc > 0 else 0
                chg = c - pc
                ampl = ((h - l) / pc * 100) if pc > 0 else 0

                rows.append({
                    'datetime': row['datetime'],
                    'open': round(o, 2), 'high': round(h, 2),
                    'low': round(l, 2), 'close': round(c, 2),
                    'volume': int(v), 'openinterest': 0,
                    'amount': round(a, 2), 'amplitude': round(ampl, 2),
                    'change_percent': round(pct_chg, 2),
                    'change_amount': round(chg, 2), 'turnover_rate': 0,
                })

            return ('ok', pd.DataFrame(rows)) if rows else ('empty', None)

        except Exception as e:
            if not self._first_error_logged:
                logger.error(f"[mootdx] {stock_code} 下载异常: {str(e)[:100]}")
                self._first_error_logged = True
            return 'error', None

    # ==================== 核心更新逻辑 ====================

    def update_stock(self, stock_code: str) -> bool:
        """增量更新单只股票。返回 True=成功或无需更新, False=下载异常"""
        last_date = self.read_last_date(stock_code)
        if last_date:
            since = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            since = '2015-01-01'

        today = datetime.now().strftime('%Y-%m-%d')
        if since >= today:
            self.stats['skipped'] += 1
            return True

        import config
        pref = getattr(config, 'STOCK_DATA_SOURCE', 'auto')

        # 优先 xtdata，失败降级 mootdx
        status, df = 'error', None
        source = None

        if pref in ('xtdata', 'auto'):
            status, df = self._download_via_xtdata(stock_code, since)
            if status == 'ok':
                source = 'xtdata'

        if status != 'ok' and pref in ('mootdx', 'auto'):
            status, df = self._download_via_mootdx(stock_code, since)
            if status == 'ok':
                source = 'mootdx'

        if status == 'empty':
            # 无新数据（停牌/退市/假期/已是最新），不算失败
            self.stats['skipped'] += 1
            return True

        if status == 'error' or df is None or df.empty:
            self.stats['failed'] += 1
            self.failed_stocks.append(stock_code)
            return False

        # 写入CSV
        rows = []
        for _, row in df.iterrows():
            rows.append([
                row['datetime'], row['open'], row['high'], row['low'],
                row['close'], row['volume'], row['openinterest'],
                row['amount'], row['amplitude'], row['change_percent'],
                row['change_amount'], row['turnover_rate'],
            ])

        self.append_to_csv(stock_code, rows)

        if last_date is None:
            self.stats['new'] += 1
            logger.info(f"[+] {stock_code} 新建 {len(rows)} 条 ({source})")
        else:
            self.stats['updated'] += 1
            logger.info(f"[~] {stock_code} {since}~{today} +{len(rows)}条 ({source})")

        return True

    def update_all(self, stock_list: Optional[List[str]] = None,
                   since_date: Optional[str] = None,
                   batch_size: Optional[int] = None):
        """批量更新全部股票（先批量下载到缓存，再逐只读取写入）"""
        import config
        if stock_list is None:
            stock_list = self.get_stock_list()
        if batch_size is None:
            batch_size = getattr(config, 'STOCK_DATA_BATCH_SIZE', 100)

        total = len(stock_list)
        logger.info(f"开始更新 {total} 只股票 (批次={batch_size})")

        self.stats = {'updated': 0, 'skipped': 0, 'failed': 0, 'new': 0, 'empty': 0}
        self.failed_stocks = []
        self._first_error_logged = False
        start_time = time.time()

        # 预计算每只股票的 since_date
        stock_since = {}
        today = datetime.now().strftime('%Y-%m-%d')
        for code in stock_list:
            last = self.read_last_date(code)
            if last:
                since = (datetime.strptime(last, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                since = '2015-01-01'
            stock_since[code] = since

        for i in range(0, total, batch_size):
            batch = stock_list[i:i + batch_size]

            for stock_code in batch:
                try:
                    self.update_stock(stock_code)
                except Exception as e:
                    self.stats['failed'] += 1
                    self.failed_stocks.append(stock_code)
                    if not self._first_error_logged:
                        logger.error(f"[!] {stock_code} 异常: {str(e)[:120]}")
                        self._first_error_logged = True

            elapsed = time.time() - start_time
            done = min(i + batch_size, total)
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            success = self.stats['updated'] + self.stats['new']
            logger.info(f"进度: {done}/{total} ({done/total*100:.1f}%) "
                        f"更新={success} 跳过={self.stats['skipped']} "
                        f"失败={len(self.failed_stocks)} "
                        f"速率={rate:.1f}只/s ETA={eta:.0f}s")

        self._save_metadata()
        self._save_failed()

        elapsed = time.time() - start_time
        logger.info(f"更新完成: 总计{total}只, 新增{self.stats['new']}, "
                    f"更新{self.stats['updated']}, 跳过{self.stats['skipped']}, "
                    f"失败{self.stats['failed']}, 耗时{elapsed:.0f}s")
        if self.failed_stocks:
            logger.warning(f"失败股票({len(self.failed_stocks)}只): {self.failed_stocks[:20]}"
                           f"{'...' if len(self.failed_stocks) > 20 else ''}")

    def retry_failed(self, batch_size: Optional[int] = None):
        """重试上次失败的股票"""
        if not self.failed_file.exists():
            logger.info("无失败记录")
            return

        with open(self.failed_file, 'r') as f:
            failed = json.load(f)

        if not failed:
            logger.info("无失败股票需要重试")
            return

        logger.info(f"重试 {len(failed)} 只失败股票")
        self.update_all(stock_list=failed, batch_size=batch_size)

    # ==================== 状态/元数据 ====================

    def check_status(self):
        """检查数据更新状态"""
        stocks = self.get_stock_list()
        today = datetime.now().strftime('%Y-%m-%d')

        up_to_date = 0
        outdated = 0
        empty = 0
        outdated_stocks = []

        for code in stocks:
            last = self.read_last_date(code)
            if last is None:
                empty += 1
            elif last >= today:
                up_to_date += 1
            else:
                outdated += 1
                if len(outdated_stocks) < 10:
                    outdated_stocks.append((code, last))

        print(f"\n========== 数据状态 ==========")
        print(f"股票总数:     {len(stocks)}")
        print(f"已更新至今天: {up_to_date}")
        print(f"需要更新:     {outdated}")
        print(f"无数据:       {empty}")
        print(f"\n最后更新日期: {self._read_metadata().get('last_update', '未知')}")

        if outdated_stocks:
            print(f"\n需更新样本:")
            for code, last in outdated_stocks:
                print(f"  {code}  最后: {last}")

        print(f"==============================\n")

    def _read_metadata(self) -> dict:
        if self.meta_file.exists():
            try:
                with open(self.meta_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_metadata(self):
        self.meta_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.meta_file, 'w') as f:
            json.dump({'last_update': datetime.now().strftime('%Y%m%d')}, f)

    def _save_failed(self):
        if self.failed_stocks:
            self.failed_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.failed_file, 'w') as f:
                json.dump(self.failed_stocks, f, ensure_ascii=False)
            logger.warning(f"失败股票列表已保存: {self.failed_file} ({len(self.failed_stocks)}只)")


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description='盘后全市场日线数据增量更新')
    parser.add_argument('--stock', '-s', type=str, help='更新单只股票')
    parser.add_argument('--since', type=str, help='从指定日期开始补数据 (YYYY-MM-DD)')
    parser.add_argument('--check', '-c', action='store_true', help='检查数据状态')
    parser.add_argument('--failed', '-f', action='store_true', help='重试失败股票')
    parser.add_argument('--batch', '-b', type=int, default=None, help='批量大小')
    parser.add_argument('--data-dir', '-d', type=str, default=None, help='数据目录')
    args = parser.parse_args()

    updater = StockDataUpdater(data_dir=args.data_dir)

    if args.check:
        updater.check_status()
    elif args.failed:
        updater.retry_failed(batch_size=args.batch)
    elif args.stock:
        ok = updater.update_stock(args.stock)
        status = "成功" if ok else "失败"
        print(f"{args.stock}: {status}")
    else:
        updater.update_all(batch_size=args.batch)


if __name__ == '__main__':
    main()
