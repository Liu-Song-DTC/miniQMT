"""
盘中高抛低吸策略 - 核心模块
多指标融合（布林带+RSI+MACD+成交量）日内摆动交易

架构：独立线程管理器，不通过 latest_signals 中转，直接调用 trading_executor
T+1 处理：当天买入的 shares 记入 floating_volume，卖出时只允许卖出底仓部分
底仓识别：启动时将现有持仓全部视为底仓，隔夜后昨天买的自动转为底仓
"""
import time
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional

import config
from logger import get_logger

logger = get_logger("swing_trading")


@dataclass
class SwingSession:
    """单只股票的摆动交易会话"""
    stock_code: str
    enabled: bool = True
    base_volume: int = 0              # 底仓数量（>= 前一日持有的 shares）
    floating_volume: int = 0          # 当天摆动买入尚未可卖的 shares
    today_buy_count: int = 0
    today_sell_count: int = 0
    today_buy_volume: int = 0         # 当日摆动累计买入量
    today_sell_volume: int = 0        # 当日摆动累计卖出量
    last_buy_time: float = 0.0
    last_sell_time: float = 0.0
    session_date: str = ""
    consecutive_failures: int = 0     # 连续失败计数
    failure_until: float = 0.0        # 连续失败后跳过直到此时（timestamp）

    def reset_daily(self, new_date: str):
        self.floating_volume = 0
        self.today_buy_count = 0
        self.today_sell_count = 0
        self.today_buy_volume = 0
        self.today_sell_volume = 0
        self.consecutive_failures = 0
        self.failure_until = 0.0
        self.session_date = new_date


class SwingTradingManager:
    """盘中高抛低吸策略管理器"""

    def __init__(self, position_manager, trading_executor, data_manager):
        self.position_manager = position_manager
        self.trading_executor = trading_executor
        self.data_manager = data_manager

        from swing_database import SwingDatabase
        self.db = SwingDatabase()

        self.sessions: Dict[str, SwingSession] = {}
        self.indicator_cache: Dict[str, tuple[float, dict]] = {}
        self.lock = threading.RLock()

        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_flag = False

        self.indicator_calculator = None

        self._load_base_positions()

    # ==================== 生命周期 ====================

    def start(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("摆动交易线程已在运行")
            return
        self.stop_flag = False
        self.monitor_thread = threading.Thread(
            target=self._swing_loop,
            daemon=True,
            name="SwingTradingThread",
        )
        self.monitor_thread.start()
        logger.info("摆动交易监控线程已启动")

    def stop(self):
        self.stop_flag = True
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
            logger.info("摆动交易监控线程已停止")

    def close(self):
        self.stop()
        with self.lock:
            for stock_code, session in self.sessions.items():
                self._persist_session(session)
        if self.db:
            self.db.close()
        logger.info("摆动交易管理器已关闭")

    # ==================== 基础持仓加载 ====================

    def _load_base_positions(self):
        today = datetime.now().strftime('%Y-%m-%d')
        with self.lock:
            positions = self.position_manager.get_all_positions()
            if positions is None or positions.empty:
                logger.info("摆动交易: 当前无持仓，等待建仓后自动纳入")
                return

            for _, row in positions.iterrows():
                stock_code = str(row.get('stock_code', ''))
                volume = int(row.get('volume', 0))
                if not stock_code or volume <= 0:
                    continue

                # 尝试从数据库恢复今日会话
                db_session = self.db.load_session(stock_code)
                if db_session and db_session.get('date') == today:
                    session = SwingSession(
                        stock_code=stock_code,
                        enabled=bool(db_session.get('enabled', 1)),
                        base_volume=int(db_session.get('base_volume_start', volume)),
                        today_buy_count=int(db_session.get('buy_count', 0)),
                        today_sell_count=int(db_session.get('sell_count', 0)),
                        today_buy_volume=int(db_session.get('total_buy_volume', 0)),
                        today_sell_volume=int(db_session.get('total_sell_volume', 0)),
                        consecutive_failures=int(db_session.get('consecutive_failures', 0)),
                        session_date=today,
                    )
                    # 从数据库恢复 floating_volume（当日买入但不可卖出的部分）
                    session.floating_volume = max(0, session.today_buy_volume - session.today_sell_volume)
                else:
                    session = SwingSession(
                        stock_code=stock_code,
                        base_volume=volume,
                        session_date=today,
                    )
                    self._persist_session(session)

                self.sessions[stock_code] = session
                logger.info(f"摆动交易: {stock_code} 底仓={session.base_volume}股, "
                            f"今日已买={session.today_buy_count}次, 已卖={session.today_sell_count}次")

    # ==================== 持久化 ====================

    def _persist_session(self, session: SwingSession):
        try:
            self.db.save_session({
                'stock_code': session.stock_code,
                'date': session.session_date or datetime.now().strftime('%Y-%m-%d'),
                'enabled': int(session.enabled),
                'base_volume_start': session.base_volume,
                'total_buy_volume': session.today_buy_volume,
                'total_sell_volume': session.today_sell_volume,
                'buy_count': session.today_buy_count,
                'sell_count': session.today_sell_count,
                'last_buy_time': datetime.fromtimestamp(session.last_buy_time).isoformat() if session.last_buy_time > 0 else '',
                'last_sell_time': datetime.fromtimestamp(session.last_sell_time).isoformat() if session.last_sell_time > 0 else '',
                'consecutive_failures': session.consecutive_failures,
            })
        except Exception as e:
            logger.error(f"持久化 {session.stock_code} 会话失败: {str(e)}")

    def _save_trade_record(self, stock_code, direction, price, volume, confidence, signal_detail, order_id=''):
        try:
            self.db.save_trade({
                'stock_code': stock_code,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'time': datetime.now().strftime('%H:%M:%S'),
                'direction': direction,
                'price': price,
                'volume': volume,
                'amount': price * volume,
                'confidence': confidence,
                'signal_detail': signal_detail,
                'order_id': str(order_id) if order_id else '',
            })
        except Exception as e:
            logger.error(f"保存 {stock_code} 交易记录失败: {str(e)}")

    # ==================== 日切换 ====================

    def _check_day_change(self):
        today = datetime.now().strftime('%Y-%m-%d')
        with self.lock:
            for session in self.sessions.values():
                if session.session_date and session.session_date != today:
                    old_date = session.session_date
                    # 隔夜：浮动仓位转底仓
                    session.base_volume += session.floating_volume
                    session.reset_daily(today)
                    self._persist_session(session)
                    logger.info(f"[日切换] {session.stock_code}: {old_date} -> {today}, "
                                f"浮动{max(0, session.base_volume - session.base_volume)}股转底仓, 底仓={session.base_volume}股")

    # ==================== 活跃股票列表 ====================

    def _get_active_stocks(self):
        stocks = []
        if config.SWING_STOCK_POOL:
            stocks = list(config.SWING_STOCK_POOL)
        else:
            positions = self.position_manager.get_all_positions()
            if positions is not None and not positions.empty:
                stocks = positions['stock_code'].tolist()

        # 确保有 session
        with self.lock:
            for stock_code in stocks:
                stock_code = str(stock_code)
                if stock_code not in self.sessions:
                    position = self.position_manager.get_position(stock_code)
                    volume = int(position.get('volume', 0)) if position else 0
                    if volume > 0:
                        self.sessions[stock_code] = SwingSession(
                            stock_code=stock_code,
                            base_volume=volume,
                            session_date=datetime.now().strftime('%Y-%m-%d'),
                        )

        return [s for s in stocks if s in self.sessions and self.sessions[s].enabled]

    # ==================== 日内指标计算 ====================

    def _get_cached_indicators(self, stock_code):
        now = time.time()
        with self.lock:
            if stock_code in self.indicator_cache:
                cache_time, data = self.indicator_cache[stock_code]
                if now - cache_time < config.SWING_INDICATOR_CACHE_TTL:
                    return data

        if self.indicator_calculator is None:
            from indicator_calculator import get_indicator_calculator
            self.indicator_calculator = get_indicator_calculator()

        indicators = self.indicator_calculator.calculate_intraday_indicators(stock_code)
        if indicators is not None:
            with self.lock:
                self.indicator_cache[stock_code] = (now, indicators)

        return indicators

    # ==================== 多指标融合打分 ====================

    def _score_buy_signal(self, indicators: dict) -> tuple[int, list[str]]:
        """对买入信号打分，返回 (分数, 命中条件列表)"""
        score = 0
        details = []

        price = indicators['close']
        rsi = indicators['rsi']
        macd_hist = indicators['macd_hist']
        prev_macd_hist = indicators['prev_macd_hist']
        volume = indicators['volume']
        volume_ma = indicators['volume_ma']
        boll_lower = indicators['boll_lower']

        if boll_lower > 0 and price <= boll_lower * 1.005:
            score += 1
            details.append(f"触及下轨({price:.2f}<={boll_lower:.2f})")

        if rsi < config.SWING_RSI_OVERSOLD:
            score += 2
            details.append(f"RSI超卖({rsi:.1f}<{config.SWING_RSI_OVERSOLD})")
        if rsi < config.SWING_RSI_OVERSOLD - 5:
            score += 1
            details.append(f"RSI深度超卖({rsi:.1f})")

        if macd_hist > 0 and prev_macd_hist < 0:
            score += 2
            details.append("MACD金叉")
        if macd_hist > 0:
            score += 1
            details.append("MACD柱>0")

        if volume_ma > 0 and volume > volume_ma * config.SWING_VOLUME_SPIKE_RATIO:
            score += 1
            details.append("放量确认")

        # KDJ 低位金叉
        k = indicators.get('kdj_k', 50)
        d = indicators.get('kdj_d', 50)
        j = indicators.get('kdj_j', 50)
        prev_k = indicators.get('prev_kdj_k', 50)
        prev_d = indicators.get('prev_kdj_d', 50)
        if prev_k <= prev_d and k > d:
            if k < config.SWING_KDJ_K_OVERSOLD:
                score += 2
                details.append(f"KDJ低位金叉(K={k:.1f})")
            else:
                score += 1
                details.append(f"KDJ金叉(K={k:.1f})")
        if j < 0:
            score += 1
            details.append(f"KDJ-J超卖(J={j:.1f})")
        if k < config.SWING_KDJ_K_OVERSOLD and d < config.SWING_KDJ_K_OVERSOLD:
            score += 1
            details.append(f"KDJ超卖区(K={k:.1f},D={d:.1f})")

        return score, details

    def _score_sell_signal(self, indicators: dict) -> tuple[int, list[str]]:
        """对卖出信号打分，返回 (分数, 命中条件列表)"""
        score = 0
        details = []

        price = indicators['close']
        rsi = indicators['rsi']
        macd_hist = indicators['macd_hist']
        prev_macd_hist = indicators['prev_macd_hist']
        volume = indicators['volume']
        volume_ma = indicators['volume_ma']
        boll_upper = indicators['boll_upper']

        if boll_upper > 0 and price >= boll_upper * 0.995:
            score += 1
            details.append(f"触及上轨({price:.2f}>={boll_upper:.2f})")

        if rsi > config.SWING_RSI_OVERBOUGHT:
            score += 2
            details.append(f"RSI超买({rsi:.1f}>{config.SWING_RSI_OVERBOUGHT})")
        if rsi > config.SWING_RSI_OVERBOUGHT + 5:
            score += 1
            details.append(f"RSI深度超买({rsi:.1f})")

        if macd_hist < 0 and prev_macd_hist > 0:
            score += 2
            details.append("MACD死叉")
        if macd_hist < 0:
            score += 1
            details.append("MACD柱<0")

        if volume_ma > 0 and volume > volume_ma * config.SWING_VOLUME_SPIKE_RATIO:
            score += 1
            details.append("放量确认")

        # KDJ 高位死叉
        k = indicators.get('kdj_k', 50)
        d = indicators.get('kdj_d', 50)
        j = indicators.get('kdj_j', 50)
        prev_k = indicators.get('prev_kdj_k', 50)
        prev_d = indicators.get('prev_kdj_d', 50)
        if prev_k >= prev_d and k < d:
            if k > config.SWING_KDJ_K_OVERBOUGHT:
                score += 2
                details.append(f"KDJ高位死叉(K={k:.1f})")
            else:
                score += 1
                details.append(f"KDJ死叉(K={k:.1f})")
        if j > 100:
            score += 1
            details.append(f"KDJ-J超买(J={j:.1f})")
        if k > config.SWING_KDJ_K_OVERBOUGHT and d > config.SWING_KDJ_K_OVERBOUGHT:
            score += 1
            details.append(f"KDJ超买区(K={k:.1f},D={d:.1f})")

        return score, details

    def _get_fused_signal(self, stock_code, indicators: dict) -> Optional[dict]:
        """多指标融合，返回信号 None 或 {'direction': 'buy'/'sell', 'confidence': score, ...}"""
        if indicators is None:
            return None

        buy_score, buy_details = self._score_buy_signal(indicators)
        sell_score, sell_details = self._score_sell_signal(indicators)

        logger.debug(f"[{stock_code}] 融合打分: 买入={buy_score}/8 {buy_details}, 卖出={sell_score}/8 {sell_details}")

        if buy_score >= config.SWING_BUY_SIGNAL_THRESHOLD:
            return {
                'direction': 'buy',
                'confidence': buy_score,
                'details': buy_details,
                'price': indicators['close'],
            }
        elif sell_score >= config.SWING_SELL_SIGNAL_THRESHOLD:
            return {
                'direction': 'sell',
                'confidence': sell_score,
                'details': sell_details,
                'price': indicators['close'],
            }

        return None

    # ==================== 风控校验 ====================

    def _can_buy(self, stock_code) -> tuple[bool, str]:
        with self.lock:
            session = self.sessions.get(stock_code)
            if not session or not session.enabled:
                return False, "摆动交易未启用"

            if session.failure_until > 0 and time.time() < session.failure_until:
                return False, f"连续失败冷却中 (剩余{int(session.failure_until - time.time())}s)"

            if session.today_buy_count >= config.SWING_MAX_DAILY_BUYS:
                return False, f"已达每日最大买入次数({config.SWING_MAX_DAILY_BUYS})"

            if session.last_buy_time > 0:
                elapsed = time.time() - session.last_buy_time
                if elapsed < config.SWING_BUY_COOLDOWN:
                    return False, f"买入冷却中 (还需{int(config.SWING_BUY_COOLDOWN - elapsed)}s)"

        position = self.position_manager.get_position(stock_code)
        if not position:
            return False, "无持仓"

        current_value = float(position.get('market_value', 0))
        buy_volume = max(int(session.base_volume * config.SWING_BUY_VOLUME_RATIO / 100) * 100, 100)
        buy_amount = buy_volume * (self.data_manager.get_latest_data(stock_code) or {}).get('lastPrice', 0) or 0
        if current_value + buy_amount > config.MAX_POSITION_VALUE:
            return False, f"将超过最大持仓市值({config.MAX_POSITION_VALUE})"

        return True, "OK"

    def _can_sell(self, stock_code) -> tuple[bool, str]:
        with self.lock:
            session = self.sessions.get(stock_code)
            if not session or not session.enabled:
                return False, "摆动交易未启用"

            if session.failure_until > 0 and time.time() < session.failure_until:
                return False, f"连续失败冷却中 (剩余{int(session.failure_until - time.time())}s)"

            if session.today_sell_count >= config.SWING_MAX_DAILY_SELLS:
                return False, f"已达每日最大卖出次数({config.SWING_MAX_DAILY_SELLS})"

            if session.last_sell_time > 0:
                elapsed = time.time() - session.last_sell_time
                if elapsed < config.SWING_SELL_COOLDOWN:
                    return False, f"卖出冷却中 (还需{int(config.SWING_SELL_COOLDOWN - elapsed)}s)"

        position = self.position_manager.get_position(stock_code)
        if not position:
            return False, "无持仓"

        total_volume = int(position.get('volume', 0))
        available = int(position.get('available', 0))

        with self.lock:
            session = self.sessions.get(stock_code)
            if not session:
                return False, "无会话"

            # T+1：不能卖出今天买入的部分（模拟模式下允许T+0）
            if not getattr(config, 'ENABLE_SIMULATION_MODE', False):
                sellable_base = total_volume - session.floating_volume
                if sellable_base <= 0:
                    return False, "全部为当日买入(T+1锁定)"

            if available < config.SWING_MIN_SELL_VOLUME:
                return False, f"可用股数不足({available}<{config.SWING_MIN_SELL_VOLUME})"

        # 最小盈利检查
        cost_price = float(position.get('cost_price', 0))
        if cost_price > 0:
            latest = self.data_manager.get_latest_data(stock_code)
            current_price = latest.get('lastPrice', 0) if latest else 0
            if current_price > 0 and current_price < cost_price * (1 + config.SWING_MIN_PROFIT_RATIO):
                return False, f"未达最小盈利要求({config.SWING_MIN_PROFIT_RATIO*100:.1f}%)"

        return True, "OK"

    # ==================== 信号执行 ====================

    def execute_swing_signal(self, stock_code, signal: dict):
        direction = signal['direction']
        confidence = signal['confidence']
        trigger_price = signal['price']
        details = signal.get('details', [])

        logger.info(f"[SWING] {stock_code} {direction.upper()} 信号 (置信度={confidence}/8): {'; '.join(details)}")

        if not config.ENABLE_AUTO_OPERATION:
            logger.info(f"[SWING] {stock_code} 全局自动操作总开关关闭，忽略信号")
            return

        if not config.ENABLE_AUTO_TRADING:
            logger.info(f"[SWING] {stock_code} 自动交易开关关闭，忽略信号")
            return

        if direction == 'buy':
            self._execute_swing_buy(stock_code, trigger_price, confidence)
        elif direction == 'sell':
            self._execute_swing_sell(stock_code, trigger_price, confidence)

    def _execute_swing_buy(self, stock_code, trigger_price, confidence):
        can_buy, reason = self._can_buy(stock_code)
        if not can_buy:
            logger.info(f"[SWING] {stock_code} 买入被拦截: {reason}")
            if '冷却' not in reason:
                self._record_failure(stock_code)
            return

        with self.lock:
            session = self.sessions[stock_code]
            buy_volume = max(int(session.base_volume * config.SWING_BUY_VOLUME_RATIO / 100) * 100,
                             config.SWING_MIN_BUY_VOLUME)
            buy_amount = buy_volume * trigger_price

        logger.info(f"[SWING] {stock_code} 摆动买入: {buy_volume}股, 金额~{buy_amount:.2f}")

        is_simulation = getattr(config, 'ENABLE_SIMULATION_MODE', True)
        strategy = 'swing_simu' if is_simulation else 'swing'

        try:
            order_id = self.trading_executor.buy_stock(
                stock_code,
                amount=buy_amount,
                price_type=5,
                strategy=strategy,
                signal_type='swing_buy',
                signal_info={
                    'current_price': trigger_price,
                    'confidence': confidence,
                }
            )
            if order_id:
                with self.lock:
                    session = self.sessions[stock_code]
                    session.floating_volume += buy_volume
                    session.today_buy_count += 1
                    session.today_buy_volume += buy_volume
                    session.last_buy_time = time.time()
                    session.consecutive_failures = 0
                    self._persist_session(session)

                self._save_trade_record(
                    stock_code, 'buy', trigger_price, buy_volume, confidence,
                    f'摆动买入(置信度={confidence}/8)', order_id,
                )
                logger.info(f"[SWING] {stock_code} 摆动买入成功, 订单号={order_id}")
                self.position_manager._increment_data_version()
            else:
                self._record_failure(stock_code)
                logger.error(f"[SWING] {stock_code} 摆动买入下单失败")

        except Exception as e:
            self._record_failure(stock_code)
            logger.error(f"[SWING] {stock_code} 摆动买入异常: {str(e)}")

    def _execute_swing_sell(self, stock_code, trigger_price, confidence):
        can_sell, reason = self._can_sell(stock_code)
        if not can_sell:
            logger.info(f"[SWING] {stock_code} 卖出被拦截: {reason}")
            if '冷却' not in reason and 'T+1' not in reason:
                self._record_failure(stock_code)
            return

        position = self.position_manager.get_position(stock_code)
        total_volume = int(position.get('volume', 0))
        available = int(position.get('available', 0))

        with self.lock:
            session = self.sessions[stock_code]
            sellable_base = total_volume - session.floating_volume
            sell_volume = max(int(sellable_base * config.SWING_SELL_VOLUME_RATIO / 100) * 100,
                              config.SWING_MIN_SELL_VOLUME)
            sell_volume = min(sell_volume, available, sellable_base)

        if sell_volume < config.SWING_MIN_SELL_VOLUME:
            logger.warning(f"[SWING] {stock_code} 可卖数量不足({sell_volume}<{config.SWING_MIN_SELL_VOLUME})")
            return

        logger.info(f"[SWING] {stock_code} 摆动卖出: {sell_volume}股 (底仓可卖={sellable_base}, 浮动锁定={session.floating_volume})")

        is_simulation = getattr(config, 'ENABLE_SIMULATION_MODE', True)
        strategy = 'swing_simu' if is_simulation else 'swing'

        try:
            order_id = self.trading_executor.sell_stock(
                stock_code,
                sell_volume,
                price_type=5,
                strategy=strategy,
                signal_type='swing_sell',
                signal_info={
                    'current_price': trigger_price,
                    'confidence': confidence,
                    'cost_price': position.get('cost_price', 0),
                }
            )
            if order_id:
                with self.lock:
                    session = self.sessions[stock_code]
                    session.today_sell_count += 1
                    session.today_sell_volume += sell_volume
                    session.last_sell_time = time.time()
                    session.consecutive_failures = 0
                    self._persist_session(session)

                self._save_trade_record(
                    stock_code, 'sell', trigger_price, sell_volume, confidence,
                    f'摆动卖出(置信度={confidence}/8)', order_id,
                )
                logger.info(f"[SWING] {stock_code} 摆动卖出成功, 订单号={order_id}")
                self.position_manager._increment_data_version()
            else:
                self._record_failure(stock_code)
                logger.error(f"[SWING] {stock_code} 摆动卖出下单失败")

        except Exception as e:
            self._record_failure(stock_code)
            logger.error(f"[SWING] {stock_code} 摆动卖出异常: {str(e)}")

    # ==================== 连续失败保护 ====================

    def _record_failure(self, stock_code):
        with self.lock:
            session = self.sessions.get(stock_code)
            if not session:
                return
            session.consecutive_failures += 1
            if session.consecutive_failures >= config.SWING_CONSECUTIVE_FAILURE_LIMIT:
                session.failure_until = time.time() + config.SWING_FAILURE_COOLDOWN
                logger.warning(f"[SWING] {stock_code} 连续失败{session.consecutive_failures}次, "
                               f"跳过{config.SWING_FAILURE_COOLDOWN}s")

    # ==================== 监控主循环 ====================

    def _swing_loop(self):
        logger.info("摆动交易监控循环启动, 间隔=%ds", config.SWING_MONITOR_INTERVAL)
        while not self.stop_flag:
            try:
                if not config.is_trade_time():
                    for _ in range(10):
                        if self.stop_flag:
                            break
                        time.sleep(1)
                    continue

                self._check_day_change()

                active_stocks = self._get_active_stocks()
                if active_stocks:
                    logger.debug(f"[SWING] 监控 {len(active_stocks)} 只股票")

                for stock_code in active_stocks:
                    if self.stop_flag:
                        break

                    # 检查连续失败冷却
                    with self.lock:
                        session = self.sessions.get(stock_code)
                        if session and session.failure_until > 0 and time.time() < session.failure_until:
                            continue

                    indicators = self._get_cached_indicators(stock_code)
                    if indicators is None:
                        continue

                    signal = self._get_fused_signal(stock_code, indicators)
                    if signal:
                        self.execute_swing_signal(stock_code, signal)

                    time.sleep(1)

                for _ in range(max(1, config.SWING_MONITOR_INTERVAL - len(active_stocks))):
                    if self.stop_flag:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"摆动交易循环出错: {str(e)}")
                time.sleep(30)

    # ==================== Web / 外部 API ====================

    def get_swing_status(self, stock_code=None):
        with self.lock:
            if stock_code:
                session = self.sessions.get(stock_code)
                if not session:
                    return {}
                return {
                    'stock_code': session.stock_code,
                    'enabled': session.enabled,
                    'base_volume': session.base_volume,
                    'floating_volume': session.floating_volume,
                    'today_buy_count': session.today_buy_count,
                    'today_sell_count': session.today_sell_count,
                    'today_buy_volume': session.today_buy_volume,
                    'today_sell_volume': session.today_sell_volume,
                    'consecutive_failures': session.consecutive_failures,
                }

            result = []
            for session in self.sessions.values():
                result.append({
                    'stock_code': session.stock_code,
                    'enabled': session.enabled,
                    'base_volume': session.base_volume,
                    'floating_volume': session.floating_volume,
                    'today_buy_count': session.today_buy_count,
                    'today_sell_count': session.today_sell_count,
                    'today_buy_volume': session.today_buy_volume,
                    'today_sell_volume': session.today_sell_volume,
                    'consecutive_failures': session.consecutive_failures,
                })
            return result

    def enable_swing(self, stock_code):
        with self.lock:
            if stock_code in self.sessions:
                self.sessions[stock_code].enabled = True
                self._persist_session(self.sessions[stock_code])
                logger.info(f"[SWING] {stock_code} 摆动交易已启用")
                return True
        return False

    def disable_swing(self, stock_code):
        with self.lock:
            if stock_code in self.sessions:
                self.sessions[stock_code].enabled = False
                self._persist_session(self.sessions[stock_code])
                logger.info(f"[SWING] {stock_code} 摆动交易已禁用")
                return True
        return False

    def get_recent_trades(self, stock_code=None):
        return self.db.get_recent_trades(stock_code)
