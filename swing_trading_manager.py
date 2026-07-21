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
    swing_entry_price: float = 0.0    # 摆动买入加权均价（用于卖出盈亏判断，区别于全部持仓平均成本）

    def reset_daily(self, new_date: str):
        self.floating_volume = 0
        self.today_buy_count = 0
        self.today_sell_count = 0
        self.today_buy_volume = 0
        self.today_sell_volume = 0
        self.consecutive_failures = 0
        self.failure_until = 0.0
        self.swing_entry_price = 0.0
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
        self.index_cache: tuple[float, dict] = (0, {})  # (timestamp, index_data)
        self.lock = threading.RLock()

        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_flag = False

        self.indicator_calculator = None

        self._last_heartbeat = 0.0  # 心跳日志节流

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
        today = config.now_cst().strftime('%Y-%m-%d')
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
                        swing_entry_price=float(db_session.get('swing_entry_price', 0)),
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
                'date': session.session_date or config.now_cst().strftime('%Y-%m-%d'),
                'enabled': int(session.enabled),
                'base_volume_start': session.base_volume,
                'total_buy_volume': session.today_buy_volume,
                'total_sell_volume': session.today_sell_volume,
                'buy_count': session.today_buy_count,
                'sell_count': session.today_sell_count,
                'last_buy_time': datetime.fromtimestamp(session.last_buy_time).isoformat() if session.last_buy_time > 0 else '',
                'last_sell_time': datetime.fromtimestamp(session.last_sell_time).isoformat() if session.last_sell_time > 0 else '',
                'consecutive_failures': session.consecutive_failures,
                'swing_entry_price': session.swing_entry_price,
            })
        except Exception as e:
            logger.error(f"持久化 {session.stock_code} 会话失败: {str(e)}")

    def _save_trade_record(self, stock_code, direction, price, volume, confidence, signal_detail, order_id=''):
        try:
            self.db.save_trade({
                'stock_code': stock_code,
                'date': config.now_cst().strftime('%Y-%m-%d'),
                'time': config.now_cst().strftime('%H:%M:%S'),
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
        today = config.now_cst().strftime('%Y-%m-%d')
        with self.lock:
            for session in self.sessions.values():
                if session.session_date and session.session_date != today:
                    old_date = session.session_date
                    # 隔夜：浮动仓位转底仓
                    converted = session.floating_volume
                    session.base_volume += converted
                    session.reset_daily(today)
                    self._persist_session(session)
                    logger.info(f"[日切换] {session.stock_code}: {old_date} -> {today}, "
                                f"浮动{converted}股转底仓, 底仓={session.base_volume}股")

    # ==================== 活跃股票列表 ====================

    def _get_active_stocks(self):
        stocks = []
        if config.SWING_STOCK_POOL:
            stocks = list(config.SWING_STOCK_POOL)
        else:
            positions = self.position_manager.get_all_positions()
            if positions is not None and not positions.empty:
                stocks = positions['stock_code'].tolist()

        stocks_set = {str(s) for s in stocks}

        # 确保有 session
        with self.lock:
            for stock_code in stocks_set:
                if stock_code not in self.sessions:
                    position = self.position_manager.get_position(stock_code)
                    volume = int(position.get('volume', 0)) if position else 0
                    if volume > 0:
                        self.sessions[stock_code] = SwingSession(
                            stock_code=stock_code,
                            base_volume=volume,
                            session_date=config.now_cst().strftime('%Y-%m-%d'),
                        )
                        self._persist_session(self.sessions[stock_code])

            # 清理已清仓的过期 session
            stale = [
                code for code, sess in self.sessions.items()
                if code not in stocks_set
            ]
            for code in stale:
                logger.info(f"[SWING] {code} 持仓已清仓，清理摆动交易会话")
                del self.sessions[code]

        return [s for s in stocks_set if s in self.sessions and self.sessions[s].enabled]

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

    def _is_in_freefall(self, indicators: dict) -> bool:
        """检测是否处于急跌状态（连续大阴线），避免接飞刀"""
        close = indicators.get('close', 0)
        open_price = indicators.get('open', 0)
        prev_close = indicators.get('prev_close', 0)

        if close <= 0 or open_price <= 0:
            return False

        bar_change = (close - open_price) / open_price
        if bar_change > -0.01:
            return False  # 当前K线非阴线或小阴线，不算急跌

        # 当前K线是大阴线（>1%），检查前一根
        if prev_close > 0 and open_price > 0:
            prev_bar_change = (open_price - prev_close) / prev_close
            if prev_bar_change < -0.005:
                return True  # 连续两根阴线，处于急跌

        # 当前K线跌幅 >2%，单根就算急跌
        if bar_change < -0.02:
            return True

        return False

    def _get_fused_signal(self, stock_code, indicators: dict) -> Optional[dict]:
        """多指标融合 + 趋势自适应，返回信号或 None"""
        if indicators is None:
            return None

        buy_score, buy_details = self._score_buy_signal(indicators)
        sell_score, sell_details = self._score_sell_signal(indicators)

        # 趋势识别
        slope = indicators.get('trend_slope', 0)
        threshold = config.SWING_TREND_SLOPE_THRESHOLD
        if slope > threshold:
            trend = 'up'
        elif slope < -threshold:
            trend = 'down'
        else:
            trend = 'range'

        # 趋势自适应阈值
        if trend == 'up':
            effective_buy_threshold = config.SWING_BUY_SIGNAL_THRESHOLD - config.SWING_TREND_BUY_BOOST
            effective_sell_threshold = config.SWING_SELL_SIGNAL_THRESHOLD + config.SWING_TREND_SELL_SUPPRESS
        elif trend == 'down':
            effective_buy_threshold = config.SWING_BUY_SIGNAL_THRESHOLD + config.SWING_TREND_BUY_SUPPRESS
            effective_sell_threshold = config.SWING_SELL_SIGNAL_THRESHOLD - config.SWING_TREND_SELL_BOOST
        else:
            effective_buy_threshold = config.SWING_BUY_SIGNAL_THRESHOLD
            effective_sell_threshold = config.SWING_SELL_SIGNAL_THRESHOLD

        # 节流 INFO 日志：仅当接近阈值(差1分)或超过时才记录
        near_buy = buy_score >= effective_buy_threshold - 1
        near_sell = sell_score >= effective_sell_threshold - 1
        if near_buy or near_sell:
            logger.info(f"[{stock_code}] 趋势={trend} 买入={buy_score}/{effective_buy_threshold} "
                        f"{buy_details}, 卖出={sell_score}/{effective_sell_threshold} {sell_details}, "
                        f"现价={indicators['close']:.2f}")
        else:
            logger.debug(f"[{stock_code}] 趋势={trend}(斜率={slope:.6f}) "
                         f"买入={buy_score}/{effective_buy_threshold} {buy_details}, "
                         f"卖出={sell_score}/{effective_sell_threshold} {sell_details}")

        if buy_score >= effective_buy_threshold:
            # 急跌保护：连续大阴线时不买入，等待价格企稳
            if self._is_in_freefall(indicators):
                logger.info(f"[{stock_code}] 买入信号被急跌保护拦截 "
                            f"(score={buy_score}, 价格仍在快速下跌，等待企稳)")
                return None
            return {
                'direction': 'buy',
                'confidence': buy_score,
                'details': buy_details + [f'趋势:{trend}'],
                'price': indicators['close'],
            }
        elif sell_score >= effective_sell_threshold:
            return {
                'direction': 'sell',
                'confidence': sell_score,
                'details': sell_details + [f'趋势:{trend}'],
                'price': indicators['close'],
            }

        return None

    # ==================== 大盘指数过滤器 ====================

    def _get_index_state(self) -> dict:
        """获取上证指数日内状态（带60s缓存）"""
        if not config.SWING_INDEX_ENABLED:
            return {'available': False}

        now = time.time()
        cache_time, cache_data = self.index_cache
        if cache_data and now - cache_time < config.SWING_INDICATOR_CACHE_TTL:
            return cache_data

        try:
            from xtquant import xtdata
            index_code = config.SWING_INDEX_CODE

            # 获取日线前收
            daily = xtdata.get_market_data(
                field_list=['close'], stock_list=[index_code],
                period='1d', count=2, dividend_type='front', fill_data=True,
            )
            if daily is None or daily['close'].empty or daily['close'].shape[0] < 1:
                return {'available': False}
            closes = daily['close'].iloc[:, 0].values
            previous_close = float(closes[-1]) if len(closes) >= 1 else 0

            # 获取5分钟线（用于MA20和日内涨跌）
            k5 = xtdata.get_market_data(
                field_list=['close'], stock_list=[index_code],
                period='5m', count=config.SWING_INDEX_MA_PERIOD + 5,
                dividend_type='front', fill_data=True,
            )
            if k5 is None or k5['close'].empty or k5['close'].shape[0] < 2:
                return {'available': False}
            k5_close = k5['close'].iloc[:, 0].values.astype(float)
            current_price = float(k5_close[-1])
            ma20 = float(k5_close[-min(len(k5_close), config.SWING_INDEX_MA_PERIOD):].mean())

            # 日内涨跌 = (当前价 - 昨收) / 昨收
            intraday_change = (current_price - previous_close) / previous_close if previous_close > 0 else 0

            # 获取个股级别的实时tick（如果可用）
            full_tick = xtdata.get_full_tick([index_code])
            if full_tick and index_code in full_tick:
                tick = full_tick[index_code]
                tick_price = getattr(tick, 'lastPrice', 0) or 0
                if tick_price > 0:
                    current_price = float(tick_price)
                    intraday_change = (current_price - previous_close) / previous_close if previous_close > 0 else intraday_change

            result = {
                'available': True,
                'current_price': current_price,
                'previous_close': previous_close,
                'intraday_change': intraday_change,
                'ma20': ma20,
                'above_ma20': current_price >= ma20,
            }

            with self.lock:
                self.index_cache = (now, result)
            return result

        except Exception as e:
            logger.debug(f"[INDEX] 获取指数数据失败: {str(e)}")
            return {'available': False}

    def _get_stock_intraday_change(self, stock_code) -> float:
        """获取个股的日内涨跌幅（相对昨收）"""
        try:
            from xtquant import xtdata
            daily = xtdata.get_market_data(
                field_list=['close'], stock_list=[stock_code],
                period='1d', count=2, dividend_type='front', fill_data=True,
            )
            if daily is None or daily['close'].empty or daily['close'].shape[0] < 1:
                return 0
            closes = daily['close'].iloc[:, 0].values
            prev = float(closes[-1])
            if prev <= 0:
                return 0

            tick = xtdata.get_full_tick([stock_code])
            cur = 0
            if tick and stock_code in tick:
                cur = getattr(tick[stock_code], 'lastPrice', 0) or 0
            if cur <= 0:
                return 0
            return (cur - prev) / prev
        except Exception:
            return 0

    def _apply_index_filter(self, stock_code, signal: dict) -> Optional[dict]:
        """将大盘指数状态应用于摆动信号，可能拦截或修正信号分数"""
        index = self._get_index_state()
        if not index.get('available'):
            return signal  # 指数数据不可用，放行

        direction = signal['direction']
        intraday_change = index['intraday_change']

        # 规则1: 大盘暴跌 >2.5%，禁止所有交易
        if intraday_change <= config.SWING_INDEX_BAN_ALL_DROP:
            logger.info(f"[INDEX] 大盘暴跌 {intraday_change*100:.1f}%，暂停全部摆动交易")
            return None

        if direction == 'buy':
            # 规则2: 大盘急跌 >1.5%，禁止买入
            if intraday_change <= config.SWING_INDEX_BAN_BUY_DROP:
                logger.info(f"[INDEX] {stock_code} 大盘急跌 {intraday_change*100:.1f}%，暂停买入")
                return None

            # 规则3: 大盘在MA20下方，趋势偏空，禁止买入
            if not index['above_ma20']:
                logger.info(f"[INDEX] {stock_code} 大盘({index['current_price']:.1f})在MA20({index['ma20']:.1f})下方，禁止买入")
                return None

            # 规则4: 个股弱于大盘，降低买入分数
            stock_change = self._get_stock_intraday_change(stock_code)
            diff = stock_change - intraday_change
            if diff < -config.SWING_INDEX_WEAK_THRESHOLD:
                signal = dict(signal)
                signal['confidence'] -= config.SWING_INDEX_SCORE_ADJUST
                signal['details'] = list(signal.get('details', [])) + [f'弱于大盘({diff*100:.1f}%)']
                if signal['confidence'] < config.SWING_BUY_SIGNAL_THRESHOLD:
                    logger.info(f"[INDEX] {stock_code} 买入信号被降分至{signal['confidence']}（弱于大盘{diff*100:.1f}%），低于阈值")
                    return None

        elif direction == 'sell':
            # 规则5: 大盘急涨 >1.5%，禁止卖出
            if intraday_change >= config.SWING_INDEX_BAN_SELL_RISE:
                logger.info(f"[INDEX] {stock_code} 大盘急涨 {intraday_change*100:.1f}%，禁止卖出")
                return None

            # 规则6: 个股强于大盘，降低卖出分数（持仓待涨）
            stock_change = self._get_stock_intraday_change(stock_code)
            diff = stock_change - intraday_change
            if diff > config.SWING_INDEX_STRONG_THRESHOLD:
                signal = dict(signal)
                signal['confidence'] -= config.SWING_INDEX_SCORE_ADJUST
                signal['details'] = list(signal.get('details', [])) + [f'强于大盘({diff*100:.1f}%)']
                if signal['confidence'] < config.SWING_SELL_SIGNAL_THRESHOLD:
                    logger.info(f"[INDEX] {stock_code} 卖出信号被降分至{signal['confidence']}（强于大盘{diff*100:.1f}%），低于阈值")
                    return None

        return signal

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

            # 按底仓比例计算目标买入量，四舍五入到100股整数倍
            desired = session.base_volume * config.SWING_BUY_VOLUME_RATIO
            buy_volume = max(int(desired), config.SWING_MIN_BUY_VOLUME)
            buy_volume = int(round(buy_volume / 100)) * 100
            if buy_volume < config.SWING_MIN_BUY_VOLUME:
                return False, f"底仓太小无法摆动(base={session.base_volume}股)"

            if session.today_buy_volume + buy_volume > session.base_volume * config.SWING_MAX_DAILY_BUY_VOLUME_RATIO:
                return False, f"已达每日最大买入量({config.SWING_MAX_DAILY_BUY_VOLUME_RATIO*100:.0f}%底仓)"

        position = self.position_manager.get_position(stock_code)
        if not position:
            return False, "无持仓"

        current_value = float(position.get('market_value', 0))
        latest = self.data_manager.get_latest_data(stock_code) or {}
        latest_price = latest.get('lastPrice', 0) or 0
        if latest_price > 0:
            buy_amount = buy_volume * latest_price
            if current_value + buy_amount > config.MAX_POSITION_VALUE:
                return False, f"将超过最大持仓市值({config.MAX_POSITION_VALUE})"

        return True, "OK"

    def _can_sell(self, stock_code) -> tuple[bool, str]:
        position = self.position_manager.get_position(stock_code)
        if not position:
            return False, "无持仓"

        total_volume = int(position.get('volume', 0))
        available = int(position.get('available', 0))

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

            # T+1：不能卖出今天买入的部分（模拟模式下允许T+0）
            if not getattr(config, 'ENABLE_SIMULATION_MODE', False):
                sellable_base = total_volume - session.floating_volume
                if sellable_base <= 0:
                    return False, "全部为当日买入(T+1锁定)"
            else:
                sellable_base = total_volume

            if available < config.SWING_MIN_SELL_VOLUME:
                return False, f"可用股数不足({available}<{config.SWING_MIN_SELL_VOLUME})"

            # 按可卖底仓比例计算目标卖出量，四舍五入到100股整数倍
            desired = sellable_base * config.SWING_SELL_VOLUME_RATIO
            sell_volume = max(int(desired), config.SWING_MIN_SELL_VOLUME)
            sell_volume = int(round(sell_volume / 100)) * 100
            sell_volume = min(sell_volume, available, sellable_base)

            if sell_volume < config.SWING_MIN_SELL_VOLUME:
                return False, f"可卖数量不足({sell_volume}<{config.SWING_MIN_SELL_VOLUME})"

            if session.today_sell_volume + sell_volume > session.base_volume * config.SWING_MAX_DAILY_SELL_VOLUME_RATIO:
                return False, f"已达每日最大卖出量({config.SWING_MAX_DAILY_SELL_VOLUME_RATIO*100:.0f}%底仓)"

        # 最小盈利检查：优先用摆动入场均价，无摆动仓位时用全部持仓平均成本
        with self.lock:
            swing_entry = self.sessions.get(stock_code)
            entry_price = (swing_entry.swing_entry_price if swing_entry and swing_entry.swing_entry_price > 0
                          else float(position.get('cost_price', 0)))
        if entry_price > 0:
            latest = self.data_manager.get_latest_data(stock_code)
            current_price = latest.get('lastPrice', 0) if latest else 0
            if current_price > 0 and current_price < entry_price * (1 + config.SWING_MIN_PROFIT_RATIO):
                return False, f"未达最小盈利要求({config.SWING_MIN_PROFIT_RATIO*100:.1f}%), 入场{entry_price:.2f}"

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
            desired = session.base_volume * config.SWING_BUY_VOLUME_RATIO
            buy_volume = max(int(desired), config.SWING_MIN_BUY_VOLUME)
            buy_volume = int(round(buy_volume / 100)) * 100
            buy_amount = buy_volume * trigger_price

        # 记录交易前持仓量，用于交易后成交验证
        position_before = self.position_manager.get_position(stock_code)
        prev_volume = int(position_before.get('volume', 0)) if position_before else 0

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
                # 交易后验证成交（检测部分成交）
                # 模拟模式下 simulate_buy_position 是同步的，立即生效
                # 实盘模式下需要短暂等待 QMT 回调
                if not is_simulation:
                    time.sleep(0.5)  # 给 QMT 回调一点时间
                verified, actual_volume = self._verify_position_after_trade(
                    stock_code, 'buy', buy_volume, prev_volume
                )

                if not verified:
                    logger.error(f"[SWING] {stock_code} 买入成交验证失败，不更新会话状态")
                    self._record_failure(stock_code)
                    return

                # 使用实际成交量
                effective_volume = min(actual_volume, buy_volume)

                with self.lock:
                    session = self.sessions[stock_code]
                    # 更新摆动入场加权均价
                    if session.swing_entry_price > 0 and session.today_buy_volume > 0:
                        old_total = session.swing_entry_price * session.today_buy_volume
                        session.swing_entry_price = (old_total + effective_volume * trigger_price) / (session.today_buy_volume + effective_volume)
                    else:
                        session.swing_entry_price = trigger_price
                    session.floating_volume += effective_volume
                    session.today_buy_count += 1
                    session.today_buy_volume += effective_volume
                    session.last_buy_time = time.time()
                    session.consecutive_failures = 0
                    self._persist_session(session)

                # 如果部分成交，修正会话状态
                if effective_volume < buy_volume:
                    actual_volume_for_rollback = effective_volume
                    self._rollback_session_state(stock_code, 'buy', buy_volume, effective_volume)
                    # 这里不实际回滚因为上面已经用了 effective_volume

                self._save_trade_record(
                    stock_code, 'buy', trigger_price, effective_volume, confidence,
                    f'摆动买入(置信度={confidence}/8)', order_id,
                )
                logger.info(f"[SWING] {stock_code} 摆动买入成功, 订单号={order_id}, 成交={effective_volume}股")
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
        is_simulation = getattr(config, 'ENABLE_SIMULATION_MODE', True)

        with self.lock:
            session = self.sessions[stock_code]
            # T+1：实盘不可卖今日买入；模拟允许T+0
            if is_simulation:
                sellable_base = total_volume
            else:
                sellable_base = total_volume - session.floating_volume
            desired = sellable_base * config.SWING_SELL_VOLUME_RATIO
            sell_volume = max(int(desired), config.SWING_MIN_SELL_VOLUME)
            sell_volume = int(round(sell_volume / 100)) * 100
            sell_volume = min(sell_volume, available, sellable_base)

        if sell_volume < config.SWING_MIN_SELL_VOLUME:
            logger.warning(f"[SWING] {stock_code} 可卖数量不足({sell_volume}<{config.SWING_MIN_SELL_VOLUME})")
            return

        # 记录交易前持仓量，用于交易后成交验证
        prev_volume = total_volume

        logger.info(f"[SWING] {stock_code} 摆动卖出: {sell_volume}股 (底仓可卖={sellable_base}, 浮动锁定={session.floating_volume})")

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
                # 交易后验证成交（检测部分成交）
                if not is_simulation:
                    time.sleep(0.5)
                verified, actual_volume = self._verify_position_after_trade(
                    stock_code, 'sell', sell_volume, prev_volume
                )

                if not verified:
                    logger.error(f"[SWING] {stock_code} 卖出成交验证失败，不更新会话状态")
                    self._record_failure(stock_code)
                    return

                effective_volume = min(actual_volume, sell_volume)

                with self.lock:
                    session = self.sessions[stock_code]
                    session.today_sell_count += 1
                    session.today_sell_volume += effective_volume
                    session.last_sell_time = time.time()
                    session.consecutive_failures = 0
                    self._persist_session(session)

                # 卖出后清空摆动入场价（本轮摆动结束）
                if effective_volume >= sell_volume * 0.8:  # 大部分成交则认为本轮结束
                    with self.lock:
                        session = self.sessions.get(stock_code)
                        if session:
                            session.swing_entry_price = 0.0

                self._save_trade_record(
                    stock_code, 'sell', trigger_price, effective_volume, confidence,
                    f'摆动卖出(置信度={confidence}/8)', order_id,
                )
                logger.info(f"[SWING] {stock_code} 摆动卖出成功, 订单号={order_id}, 成交={effective_volume}股")
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

    # ==================== 订单成交验证 ====================

    def _verify_position_after_trade(self, stock_code, direction, expected_volume, prev_volume):
        """交易后验证持仓是否按预期变化，检测部分成交。

        返回: (verified: bool, actual_filled: int)
        """
        position = self.position_manager.get_position(stock_code)
        if not position:
            logger.warning(f"[SWING] {stock_code} 交易后持仓消失，无法验证成交")
            return False, 0

        current_volume = int(position.get('volume', 0))

        if direction == 'buy':
            actual_filled = current_volume - prev_volume
            if actual_filled <= 0:
                logger.warning(f"[SWING] {stock_code} 买入后持仓未增加 "
                               f"(预期+{expected_volume}, 实际+{actual_filled}), 可能未成交")
                return False, actual_filled
            if actual_filled < expected_volume:
                logger.warning(f"[SWING] {stock_code} 部分成交: 预期+{expected_volume}, 实际+{actual_filled}")
                return True, actual_filled  # 部分成交也算成交，但数量需要修正
            return True, actual_filled
        else:
            actual_filled = prev_volume - current_volume
            if actual_filled <= 0:
                logger.warning(f"[SWING] {stock_code} 卖出后持仓未减少 "
                               f"(预期-{expected_volume}, 实际-{actual_filled}), 可能未成交")
                return False, actual_filled
            if actual_filled < expected_volume:
                logger.warning(f"[SWING] {stock_code} 部分成交: 预期-{expected_volume}, 实际-{actual_filled}")
                return True, actual_filled
            return True, actual_filled

    def _rollback_session_state(self, stock_code, direction, expected_volume, actual_volume):
        """部分成交时回滚/修正会话状态"""
        with self.lock:
            session = self.sessions.get(stock_code)
            if not session:
                return
            diff = expected_volume - actual_volume  # 未成交部分
            if direction == 'buy':
                session.floating_volume -= diff
                session.today_buy_volume -= diff
                # 不修改 swing_entry_price（未成交部分不应影响均价）
            elif direction == 'sell':
                session.today_sell_volume -= diff
                session.today_sell_count = max(0, session.today_sell_count)
            self._persist_session(session)
            logger.info(f"[SWING] {stock_code} 会话状态已修正: {direction} 预期{expected_volume}→实际{actual_volume}, 修正{diff}股")

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

                    # 每 5 分钟输出一次心跳：指标是否正常、各股票打分状态
                    now_ts = time.time()
                    if now_ts - self._last_heartbeat >= 300:
                        self._last_heartbeat = now_ts
                        for sc in active_stocks:
                            ind = self._get_cached_indicators(sc)
                            if ind is None:
                                logger.info(f"[SWING] {sc} 无日内K线数据，跳过")
                            else:
                                b, bd = self._score_buy_signal(ind)
                                s, sd = self._score_sell_signal(ind)
                                slope = ind.get('trend_slope', 0)
                                logger.info(f"[SWING] {sc} 价格={ind['close']:.2f} 买入={b}分 {bd}, "
                                            f"卖出={s}分 {sd}, 趋势斜率={slope:.6f}")

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
                        signal = self._apply_index_filter(stock_code, signal)
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
