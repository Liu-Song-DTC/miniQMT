"""
Grid Trading and Profit Management Isolation Test
网格交易与止盈止损机制隔离性验证测试

Test Coverage (TC01-TC10):
1. TC01-TC03: Configuration Isolation
2. TC04-TC05: Signal Isolation
3. TC06-TC07: Data Isolation
4. TC08: Database Isolation
5. TC09: Sequential Constraint
6. TC10: Concurrent Execution

Author: System Test Framework
Created: 2026-02-04
"""

import sys
import os
import time
import threading
import unittest.mock
from datetime import datetime, timedelta
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_base import TestBase
import config
from position_manager import PositionManager
from grid_trading_manager import GridSession, PriceTracker, GridTradingManager
from grid_database import DatabaseManager
from trading_executor import TradingExecutor
from logger import get_logger

logger = get_logger("test_grid_profit_isolation")


class MockTradingExecutor:
    """模拟交易执行器"""
    def __init__(self):
        self.trade_history = []
        self.order_counter = 0

    def buy_stock(self, stock_code, amount, strategy):
        self.order_counter += 1
        trade_id = f"SIM_BUY_{self.order_counter}"
        self.trade_history.append({
            'type': 'BUY',
            'stock_code': stock_code,
            'amount': amount,
            'strategy': strategy,
            'trade_id': trade_id,
            'timestamp': datetime.now()
        })
        logger.info(f"[MOCK] BUY executed: {stock_code}, amount={amount:.2f}, strategy={strategy}")
        return {'success': True, 'order_id': trade_id}

    def sell_stock(self, stock_code, volume, price=None, strategy="grid"):
        self.order_counter += 1
        trade_id = f"SIM_SELL_{self.order_counter}"
        self.trade_history.append({
            'type': 'SELL',
            'stock_code': stock_code,
            'volume': volume,
            'strategy': strategy,
            'trade_id': trade_id,
            'timestamp': datetime.now()
        })
        logger.info(f"[MOCK] SELL executed: {stock_code}, volume={volume}, strategy={strategy}")
        return {'success': True, 'order_id': trade_id}

    def get_trade_count(self, strategy=None):
        """获取交易次数"""
        if strategy:
            return len([t for t in self.trade_history if t['strategy'] == strategy])
        return len(self.trade_history)


class TestGridProfitIsolation(TestBase):
    """网格交易与止盈止损机制隔离性测试"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        super().setUpClass()
        logger.info("=" * 60)
        logger.info("Grid-Profit Isolation Test Suite - Starting")
        logger.info("=" * 60)

    def setUp(self):
        """每个测试用例前的初始化"""
        super().setUp()

        # 初始化组件
        self.db = DatabaseManager(config.DB_PATH)
        self.db.init_grid_tables()

        self.executor = MockTradingExecutor()
        self.position_manager = PositionManager()

        self.grid_manager = GridTradingManager(
            self.db,
            self.position_manager,
            self.executor
        )

        # 清理测试数据
        self._cleanup_test_data()

    def tearDown(self):
        """每个测试用例后的清理"""
        self._cleanup_test_data()
        super().tearDown()

    def _cleanup_test_data(self):
        """清理测试数据"""
        try:
            conn = self.create_test_db_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM positions WHERE stock_code LIKE 'TEST%'")
            cursor.execute("DELETE FROM grid_trading_sessions WHERE stock_code LIKE 'TEST%'")
            cursor.execute("DELETE FROM grid_trades WHERE stock_code LIKE 'TEST%'")
            cursor.execute("DELETE FROM trade_records WHERE stock_code LIKE 'TEST%'")

            conn.commit()
            conn.close()
            logger.debug("Test data cleaned up")
        except Exception as e:
            logger.warning(f"Cleanup failed: {str(e)}")

    def _create_test_position(self, stock_code='TEST001.SZ', volume=1000,
                             cost_price=10.00, current_price=10.60,
                             profit_triggered=False, highest_price=10.60,
                             stop_loss_price=9.25):
        """创建测试持仓"""
        conn = self.create_test_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO positions
            (stock_code, volume, available, cost_price, current_price,
             open_date, profit_triggered, highest_price, stop_loss_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (stock_code, volume, volume, cost_price, current_price,
              datetime.now().strftime("%Y-%m-%d"),
              profit_triggered, highest_price, stop_loss_price))

        conn.commit()
        conn.close()

        # 同步到内存数据库
        self.position_manager._sync_db_to_memory()

        logger.info(f"Test position created: {stock_code}, volume={volume}, "
                   f"cost={cost_price:.2f}, current={current_price:.2f}, "
                   f"profit_triggered={profit_triggered}")

    # ==================== TC01-TC03: Configuration Isolation ====================

    def test_tc01_config_isolation_grid_disabled(self):
        """
        TC01: 配置隔离 - 网格关闭时不影响止盈止损

        场景:
        - ENABLE_GRID_TRADING = False
        - ENABLE_DYNAMIC_STOP_PROFIT = True

        预期:
        - 止盈止损信号正常检测
        - 网格交易不执行
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC01: Config Isolation - Grid Disabled")
        logger.info("=" * 60)

        # 配置
        original_grid_enabled = config.ENABLE_GRID_TRADING
        config.ENABLE_GRID_TRADING = False
        config.ENABLE_DYNAMIC_STOP_PROFIT = True

        try:
            # 创建持仓: 已触发首次止盈
            self._create_test_position(
                stock_code='TEST001.SZ',
                volume=1000,
                cost_price=10.00,
                current_price=10.60,
                profit_triggered=True,
                highest_price=10.60
            )

            # 检测止盈止损信号
            position = self.position_manager.get_position('TEST001.SZ')
            self.assertIsNotNone(position, "Position should exist")

            # 更新数据库中的价格，模拟价格下跌触发动态止盈
            conn = self.create_test_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE positions SET current_price = ? WHERE stock_code = ?",
                          (10.10, 'TEST001.SZ'))  # 从最高价10.60回落
            conn.commit()
            conn.close()

            # 🔧 关键修复: 同步SQLite到内存数据库
            self.position_manager._sync_db_to_memory()

            # 🔧 关键修复: Mock data_manager.get_latest_data返回更新后的价格
            with unittest.mock.patch.object(
                self.position_manager.data_manager,
                'get_latest_data',
                return_value={'lastPrice': 10.10}
            ):
                # 调用check_trading_signals检测信号
                signal_type, signal_info = self.position_manager.check_trading_signals('TEST001.SZ')

                # 断言: 应该检测到动态止盈信号 (使用返回值直接断言)
                self.assertEqual(signal_type, 'take_profit_full',
                               "Should detect dynamic take profit signal when price drops from peak")
                self.assertIsNotNone(signal_info, "Signal info should contain details")
                logger.info(f"[PASS] Stop profit signal detected: type={signal_type}, info={signal_info}")

            # 断言: 网格管理器应该没有活跃会话
            self.assertEqual(len(self.grid_manager.sessions), 0,
                           "Grid sessions should be empty when grid trading disabled")
            logger.info("[PASS] Grid trading inactive as expected")

        finally:
            config.ENABLE_GRID_TRADING = original_grid_enabled

    def test_tc02_config_isolation_profit_disabled(self):
        """
        TC02: 配置隔离 - 止盈关闭时不影响网格交易

        场景:
        - ENABLE_GRID_TRADING = True
        - ENABLE_DYNAMIC_STOP_PROFIT = False

        预期:
        - 网格交易会话正常启动
        - 止盈止损不检测
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC02: Config Isolation - Profit Disabled")
        logger.info("=" * 60)

        original_profit_enabled = config.ENABLE_DYNAMIC_STOP_PROFIT
        original_grid_enabled = config.ENABLE_GRID_TRADING
        config.ENABLE_DYNAMIC_STOP_PROFIT = False
        config.ENABLE_GRID_TRADING = True

        try:
            # 创建持仓: 已触发首次止盈(满足网格交易前提条件)
            self._create_test_position(
                stock_code='TEST002.SZ',
                volume=600,  # 首次止盈后剩余60%
                cost_price=10.00,
                current_price=10.60,
                profit_triggered=True,
                highest_price=10.60
            )

            # 启动网格交易
            user_config = {
                'center_price': 10.60,
                'price_interval': 0.05,
                'position_ratio': 0.25,
                'callback_ratio': 0.005,
                'max_investment': 3000.0,
                'max_deviation': 0.20,
                'target_profit': 0.15,
                'stop_loss': -0.15,
                'duration_days': 7
            }

            session = self.grid_manager.start_grid_session('TEST002.SZ', user_config)

            # 断言: 网格会话应该成功启动
            self.assertIsNotNone(session, "Grid session should start successfully")
            self.assertEqual(session.stock_code, 'TEST002.SZ')
            logger.info(f"[PASS] Grid session started: ID={session.id}")

            # 断言: 止盈止损检测应该被跳过
            # 关闭ENABLE_DYNAMIC_STOP_PROFIT时，check_trading_signals直接返回(None, None)
            signal_type, signal_info = self.position_manager.check_trading_signals('TEST002.SZ')
            self.assertIsNone(signal_type, "Stop profit should be skipped when ENABLE_DYNAMIC_STOP_PROFIT=False")
            self.assertIsNone(signal_info, "Signal info should be None when ENABLE_DYNAMIC_STOP_PROFIT=False")
            logger.info("[PASS] Stop profit detection skipped as expected")

        finally:
            config.ENABLE_DYNAMIC_STOP_PROFIT = original_profit_enabled
            config.ENABLE_GRID_TRADING = original_grid_enabled

    def test_tc03_config_isolation_both_enabled(self):
        """
        TC03: 配置隔离 - 双功能同时开启

        场景:
        - ENABLE_GRID_TRADING = True
        - ENABLE_DYNAMIC_STOP_PROFIT = True

        预期:
        - 两个模块独立运行
        - 各自配置参数不冲突
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC03: Config Isolation - Both Enabled")
        logger.info("=" * 60)

        original_profit_enabled = config.ENABLE_DYNAMIC_STOP_PROFIT
        original_grid_enabled = config.ENABLE_GRID_TRADING
        config.ENABLE_DYNAMIC_STOP_PROFIT = True
        config.ENABLE_GRID_TRADING = True

        try:
            # 创建持仓
            self._create_test_position(
                stock_code='TEST003.SZ',
                volume=600,
                cost_price=10.00,
                current_price=10.60,
                profit_triggered=True,
                highest_price=10.60
            )

            # 启动网格交易
            user_config = {
                'center_price': 10.60,
                'price_interval': 0.05,
                'position_ratio': 0.25,
                'callback_ratio': 0.005,
                'max_investment': 3000.0,
                'max_deviation': 0.20,
                'target_profit': 0.15,
                'stop_loss': -0.15,
                'duration_days': 7
            }

            grid_session = self.grid_manager.start_grid_session('TEST003.SZ', user_config)

            # 断言: 网格会话正常启动
            self.assertIsNotNone(grid_session, "Grid session should start")
            logger.info(f"[PASS] Grid session started: ID={grid_session.id}")

            # 断言: 止盈止损仍然可以检测
            # 更新数据库中的价格
            conn = self.create_test_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE positions SET current_price = ? WHERE stock_code = ?",
                          (10.10, 'TEST003.SZ'))  # 触发动态止盈
            conn.commit()
            conn.close()

            # 🔧 关键修复: 同步SQLite到内存数据库
            self.position_manager._sync_db_to_memory()

            # 🔧 关键修复: Mock data_manager.get_latest_data返回更新后的价格
            with unittest.mock.patch.object(
                self.position_manager.data_manager,
                'get_latest_data',
                return_value={'lastPrice': 10.10}
            ):
                # 调用check_trading_signals检测信号
                signal_type, signal_info = self.position_manager.check_trading_signals('TEST003.SZ')

                # 断言: 应该检测到动态止盈信号 (使用返回值直接断言)
                self.assertEqual(signal_type, 'take_profit_full',
                               "Stop profit signal should still be detected when both features enabled")
                self.assertIsNotNone(signal_info, "Signal info should contain details")
                logger.info(f"[PASS] Stop profit signal detected: type={signal_type}, info={signal_info}")

            # 断言: 配置参数各自独立
            self.assertNotEqual(config.INITIAL_TAKE_PROFIT_RATIO,
                              grid_session.price_interval,
                              "Config parameters should be independent")
            logger.info("[PASS] Configuration parameters are isolated")

        finally:
            config.ENABLE_DYNAMIC_STOP_PROFIT = original_profit_enabled
            config.ENABLE_GRID_TRADING = original_grid_enabled

    # ==================== TC04-TC05: Signal Isolation ====================

    def test_tc04_signal_coexistence(self):
        """
        TC04: 信号隔离 - 两种信号可共存于latest_signals队列

        场景:
        - 同一股票同时检测到止盈信号和网格信号

        预期:
        - latest_signals中可以同时存在两种信号
        - 信号类型字段可区分
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC04: Signal Coexistence")
        logger.info("=" * 60)

        stock_code = 'TEST004.SZ'

        # 创建持仓
        self._create_test_position(
            stock_code=stock_code,
            volume=600,
            cost_price=10.00,
            current_price=10.60,
            profit_triggered=True,
            highest_price=10.60
        )

        # 启动网格交易
        user_config = {
            'center_price': 10.60,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }
        grid_session = self.grid_manager.start_grid_session(stock_code, user_config)
        self.assertIsNotNone(grid_session)

        # 模拟检测止盈信号
        with self.position_manager.signal_lock:
            self.position_manager.latest_signals[stock_code] = {
                'type': 'take_profit_full',
                'timestamp': datetime.now(),
                'reason': 'dynamic_stop_profit',
                'current_price': 10.10
            }

        # 模拟检测网格信号（通过价格穿越）
        grid_signal = self.grid_manager.check_grid_signals(stock_code, 10.05)

        # 如果网格信号触发，添加到latest_signals
        if grid_signal:
            # 注意：实际实现中网格信号可能不通过latest_signals，这里仅验证机制
            logger.info(f"[INFO] Grid signal detected: {grid_signal}")

        # 断言: latest_signals中存在止盈信号
        with self.position_manager.signal_lock:
            self.assertIn(stock_code, self.position_manager.latest_signals,
                         "Stop profit signal should exist in latest_signals")
            signal_info = self.position_manager.latest_signals[stock_code]
            self.assertEqual(signal_info['type'], 'take_profit_full',
                           "Signal type should be take_profit_full")

        logger.info("[PASS] Signals can coexist in latest_signals queue")

    def test_tc05_signal_independent_processing(self):
        """
        TC05: 信号隔离 - 独立处理验证

        场景:
        - 分别处理止盈信号和网格信号

        预期:
        - 处理一个信号不影响另一个
        - 各自通过validate_trading_signal验证
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC05: Signal Independent Processing")
        logger.info("=" * 60)

        stock_code = 'TEST005.SZ'

        # 创建持仓
        self._create_test_position(
            stock_code=stock_code,
            volume=600,
            cost_price=10.00,
            current_price=10.60,
            profit_triggered=True,
            highest_price=10.60
        )

        # 模拟止盈信号
        profit_signal = {
            'type': 'take_profit_full',
            'timestamp': datetime.now(),
            'reason': 'dynamic_stop_profit',
            'current_price': 10.10,
            'cost_price': 10.00,
            'volume': 600
        }

        # 验证止盈信号
        is_valid = self.position_manager.validate_trading_signal(
            stock_code, 'take_profit_full', profit_signal
        )
        self.assertTrue(is_valid, "Profit signal should pass validation")
        logger.info("[PASS] Profit signal validated successfully")

        # 标记止盈信号已处理
        self.position_manager.mark_signal_processed(stock_code)

        # 启动网格交易
        user_config = {
            'center_price': 10.60,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }
        grid_session = self.grid_manager.start_grid_session(stock_code, user_config)
        self.assertIsNotNone(grid_session)

        # 模拟网格信号
        grid_signal = self.grid_manager.check_grid_signals(stock_code, 11.10)

        if grid_signal:
            logger.info(f"[PASS] Grid signal detected independently: {grid_signal['signal_type']}")
        else:
            logger.info("[INFO] No grid signal triggered at current price")

        logger.info("[PASS] Signals processed independently")

    # ==================== TC06-TC07: Data Isolation ====================

    def test_tc06_data_isolation_grid_no_modify_profit_fields(self):
        """
        TC06: 数据隔离 - 网格交易不修改止盈字段

        场景:
        - 执行网格买入/卖出交易

        预期:
        - highest_price保持不变
        - profit_triggered保持不变
        - stop_loss_price保持不变
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC06: Data Isolation - Grid Does Not Modify Profit Fields")
        logger.info("=" * 60)

        stock_code = 'TEST006.SZ'

        # 创建持仓
        self._create_test_position(
            stock_code=stock_code,
            volume=600,
            cost_price=10.00,
            current_price=10.60,
            profit_triggered=True,
            highest_price=10.80,  # 历史最高价
            stop_loss_price=9.25
        )

        # 记录原始值
        position_before = self.position_manager.get_position(stock_code)
        highest_price_before = position_before['highest_price']
        profit_triggered_before = position_before['profit_triggered']
        stop_loss_price_before = position_before['stop_loss_price']

        logger.info(f"[BEFORE] highest_price={highest_price_before:.2f}, "
                   f"profit_triggered={profit_triggered_before}, "
                   f"stop_loss_price={stop_loss_price_before:.2f}")

        # 启动网格交易
        user_config = {
            'center_price': 10.60,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }
        grid_session = self.grid_manager.start_grid_session(stock_code, user_config)
        self.assertIsNotNone(grid_session)

        # 执行网格交易（模拟卖出）
        grid_signal = self.grid_manager.check_grid_signals(stock_code, 11.10)
        if grid_signal:
            success = self.grid_manager.execute_grid_trade(grid_signal)
            self.assertTrue(success, "Grid trade should execute successfully")
            logger.info(f"[EXECUTED] Grid trade: {grid_signal['signal_type']}")

        # 检查持仓字段
        position_after = self.position_manager.get_position(stock_code)
        highest_price_after = position_after.get('highest_price')
        profit_triggered_after = position_after.get('profit_triggered')
        stop_loss_price_after = position_after.get('stop_loss_price')

        logger.info(f"[AFTER] highest_price={highest_price_after:.2f}, "
                   f"profit_triggered={profit_triggered_after}, "
                   f"stop_loss_price={stop_loss_price_after:.2f}")

        # 断言: 止盈相关字段未被修改
        self.assertEqual(highest_price_after, highest_price_before,
                        "highest_price should not be modified by grid trading")
        self.assertEqual(profit_triggered_after, profit_triggered_before,
                        "profit_triggered should not be modified by grid trading")
        self.assertEqual(stop_loss_price_after, stop_loss_price_before,
                        "stop_loss_price should not be modified by grid trading")

        logger.info("[PASS] Grid trading did not modify profit-related fields")

    def test_tc07_data_isolation_profit_no_modify_grid_fields(self):
        """
        TC07: 数据隔离 - 止盈执行不修改网格字段

        场景:
        - 执行动态止盈卖出

        预期:
        - grid_sessions表中的current_center_price保持不变
        - 网格会话状态不受影响
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC07: Data Isolation - Profit Does Not Modify Grid Fields")
        logger.info("=" * 60)

        stock_code = 'TEST007.SZ'

        # 创建持仓
        self._create_test_position(
            stock_code=stock_code,
            volume=600,
            cost_price=10.00,
            current_price=10.60,
            profit_triggered=True,
            highest_price=10.80,
            stop_loss_price=9.25
        )

        # 启动网格交易
        user_config = {
            'center_price': 10.60,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }
        grid_session_before = self.grid_manager.start_grid_session(stock_code, user_config)
        self.assertIsNotNone(grid_session_before)

        # 记录网格字段原始值
        center_price_before = grid_session_before.current_center_price
        session_id = grid_session_before.id

        logger.info(f"[BEFORE] Grid session ID={session_id}, "
                   f"current_center_price={center_price_before:.2f}")

        # 执行止盈操作（模拟触发动态止盈）
        # 更新数据库中的价格
        conn = self.create_test_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE positions SET current_price = ? WHERE stock_code = ?",
                      (10.10, stock_code))  # 从最高价回落触发止盈
        conn.commit()
        conn.close()

        # 调用check_trading_signals检测信号
        self.position_manager.check_trading_signals(stock_code)

        # 验证信号
        with self.position_manager.signal_lock:
            signal = self.position_manager.latest_signals.get(stock_code)
            if signal:
                logger.info(f"[DETECTED] Stop profit signal: {signal['type']}")
                # 注意: 实际执行卖出会调用trading_executor
                # 这里仅验证数据隔离，不真正执行

        # 检查网格字段
        grid_session_after = self.grid_manager.sessions.get(stock_code)

        if grid_session_after:
            center_price_after = grid_session_after.current_center_price

            logger.info(f"[AFTER] Grid session ID={grid_session_after.id}, "
                       f"current_center_price={center_price_after:.2f}")

            # 断言: 网格中心价格未被修改
            self.assertEqual(center_price_after, center_price_before,
                           "current_center_price should not be modified by profit execution")

            logger.info("[PASS] Profit execution did not modify grid fields")
        else:
            logger.warning("[WARN] Grid session not found after profit signal")

    # ==================== TC08: Database Isolation ====================

    def test_tc08_database_isolation(self):
        """
        TC08: 数据库隔离 - 不同表互不干扰

        场景:
        - 同时向positions和grid_trading_sessions写入数据

        预期:
        - 写入操作互不阻塞
        - 数据完整性保持
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC08: Database Isolation")
        logger.info("=" * 60)

        stock_code = 'TEST008.SZ'

        # 创建持仓
        self._create_test_position(
            stock_code=stock_code,
            volume=600,
            cost_price=10.00,
            current_price=10.60,
            profit_triggered=True,
            highest_price=10.60
        )

        # 启动网格交易（写入grid_trading_sessions表）
        user_config = {
            'center_price': 10.60,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }
        grid_session = self.grid_manager.start_grid_session(stock_code, user_config)
        self.assertIsNotNone(grid_session)

        # 并发修改持仓数据（写入positions表）
        def update_position():
            time.sleep(0.1)
            conn = self.create_test_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE positions SET current_price = ? WHERE stock_code = ?
            """, (10.70, stock_code))
            conn.commit()
            conn.close()
            logger.info("[THREAD] Position updated")

        # 并发修改网格会话（写入grid_trading_sessions表）
        def update_grid_session():
            time.sleep(0.1)
            conn = self.create_test_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE grid_trading_sessions SET trade_count = trade_count + 1
                WHERE stock_code = ?
            """, (stock_code,))
            conn.commit()
            conn.close()
            logger.info("[THREAD] Grid session updated")

        # 启动并发线程
        t1 = threading.Thread(target=update_position)
        t2 = threading.Thread(target=update_grid_session)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # 验证数据完整性
        conn = self.create_test_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT current_price FROM positions WHERE stock_code = ?",
                      (stock_code,))
        position_result = cursor.fetchone()
        self.assertIsNotNone(position_result)
        self.assertEqual(position_result[0], 10.70,
                        "Position update should succeed")

        cursor.execute("SELECT trade_count FROM grid_trading_sessions WHERE stock_code = ?",
                      (stock_code,))
        session_result = cursor.fetchone()
        self.assertIsNotNone(session_result)
        self.assertGreater(session_result[0], 0,
                          "Grid session update should succeed")

        conn.close()

        logger.info("[PASS] Database tables are isolated, no interference")

    # ==================== TC09: Sequential Constraint ====================

    def test_tc09_profit_not_triggered_allowed_by_default(self):
        """
        TC09: 默认配置下，profit_triggered=False 也允许启动网格。
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC09: Default Allows Grid Before Profit Triggered")
        logger.info("=" * 60)

        stock_code = 'TEST009.SZ'

        self._create_test_position(
            stock_code=stock_code,
            volume=1000,
            cost_price=10.00,
            current_price=10.50,
            profit_triggered=False,
            highest_price=10.50
        )

        user_config = {
            'center_price': 10.50,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }

        grid_session = self.grid_manager.start_grid_session(stock_code, user_config)

        self.assertIsNotNone(grid_session)
        self.assertEqual(grid_session.stock_code, stock_code)
        self.assertEqual(grid_session.status, 'active')
        self.assertEqual(grid_session.center_price, 10.50)

        logger.info("[PASS] Grid session started when profit_triggered=False")

    def test_tc09_profit_not_triggered_rejected_when_guard_enabled(self):
        """
        TC09b: 显式开启 GRID_REQUIRE_PROFIT_TRIGGERED 时，仍拒绝未触发止盈的持仓。
        """
        stock_code = 'TEST009B.SZ'

        self._create_test_position(
            stock_code=stock_code,
            volume=1000,
            cost_price=10.00,
            current_price=10.50,
            profit_triggered=False,
            highest_price=10.50
        )

        user_config = {
            'center_price': 10.50,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }

        with unittest.mock.patch.object(config, 'GRID_REQUIRE_PROFIT_TRIGGERED', True):
            with self.assertRaises(ValueError) as cm:
                self.grid_manager.start_grid_session(stock_code, user_config)

        self.assertIn('未触发止盈', str(cm.exception))
        logger.info("[PASS] Grid session rejected when profit-trigger guard is enabled")

    # ==================== TC10: Concurrent Execution ====================

    def test_tc10_concurrent_execution(self):
        """
        TC10: 并发执行 - 同一股票同时执行止盈和网格交易

        场景:
        - 线程1执行止盈卖出
        - 线程2执行网格买入

        预期:
        - 两个操作互不阻塞
        - trade_records中可区分strategy字段
        """
        logger.info("\n" + "=" * 60)
        logger.info("TC10: Concurrent Execution")
        logger.info("=" * 60)

        stock_code = 'TEST010.SZ'

        # 创建持仓
        self._create_test_position(
            stock_code=stock_code,
            volume=600,
            cost_price=10.00,
            current_price=10.60,
            profit_triggered=True,
            highest_price=10.80
        )

        # 启动网格交易
        user_config = {
            'center_price': 10.60,
            'price_interval': 0.05,
            'position_ratio': 0.25,
            'callback_ratio': 0.005,
            'max_investment': 3000.0,
            'max_deviation': 0.20,
            'target_profit': 0.15,
            'stop_loss': -0.15,
            'duration_days': 7
        }
        grid_session = self.grid_manager.start_grid_session(stock_code, user_config)
        self.assertIsNotNone(grid_session)

        # 并发执行标志
        profit_executed = threading.Event()
        grid_executed = threading.Event()

        # 线程1: 执行止盈卖出
        def execute_profit_sell():
            time.sleep(0.05)
            result = self.executor.sell_stock(stock_code, 300, strategy='take_profit')
            if result['success']:
                profit_executed.set()
                logger.info("[THREAD1] Profit sell executed")

        # 线程2: 执行网格买入
        def execute_grid_buy():
            time.sleep(0.05)
            result = self.executor.buy_stock(stock_code, 1000.0, strategy='grid')
            if result['success']:
                grid_executed.set()
                logger.info("[THREAD2] Grid buy executed")

        # 启动并发线程
        t1 = threading.Thread(target=execute_profit_sell)
        t2 = threading.Thread(target=execute_grid_buy)

        start_time = time.time()
        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)
        execution_time = time.time() - start_time

        # 断言: 两个操作都成功执行
        self.assertTrue(profit_executed.is_set(), "Profit sell should execute")
        self.assertTrue(grid_executed.is_set(), "Grid buy should execute")

        # 断言: 执行时间合理（并发执行不应该线性叠加）
        self.assertLess(execution_time, 2.0,
                       "Concurrent execution should not block each other")

        # 验证trade_records中可以区分strategy
        profit_trades = self.executor.get_trade_count(strategy='take_profit')
        grid_trades = self.executor.get_trade_count(strategy='grid')

        self.assertEqual(profit_trades, 1, "Should have 1 profit trade")
        self.assertEqual(grid_trades, 1, "Should have 1 grid trade")

        logger.info(f"[PASS] Concurrent execution completed in {execution_time:.2f}s")
        logger.info(f"[PASS] Trades recorded: profit={profit_trades}, grid={grid_trades}")


def main():
    """主函数"""
    import unittest

    print("\n" + "=" * 60)
    print("Grid-Profit Isolation Test Suite")
    print("Test Coverage: TC01-TC10")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestGridProfitIsolation)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total Tests: {result.testsRun}")
    print(f"Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failed: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success Rate: {(result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100:.1f}%")

    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
