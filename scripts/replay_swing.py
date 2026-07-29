#!/usr/bin/env python3
"""
摆动交易离线回放调参工具

加载盘中录制的5分钟K线CSV数据，逐根K线运行摆动交易信号逻辑，
支持参数覆盖，输出完整的打分轨迹和模拟交易结果。

用法:
    python scripts/replay_swing.py data/swing_replay/300394.SZ_20260723.csv

    # 覆盖参数
    python scripts/replay_swing.py data/swing_replay/300394.SZ_20260723.csv \
        --buy-threshold 4 --sell-threshold 4 --buy-cooldown 180

    # 从JSON文件加载参数
    python scripts/replay_swing.py data/swing_replay/300394.SZ_20260723.csv \
        --params custom_params.json
"""
import argparse
import json
import os
import sys
import numpy as np
import pandas as pd

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MyTT import MA, MACD, RSI, KDJ, BOLL


# ==================== 默认参数（与 config.py 一致） ====================
DEFAULT_PARAMS = {
    'SWING_BOLL_PERIOD': 20,
    'SWING_BOLL_STD': 2.0,
    'SWING_RSI_PERIOD': 14,
    'SWING_RSI_OVERSOLD': 30,
    'SWING_RSI_OVERBOUGHT': 70,
    'SWING_MACD_FAST': 6,
    'SWING_MACD_SLOW': 13,
    'SWING_MACD_SIGNAL': 5,
    'SWING_KDJ_PERIOD': 9,
    'SWING_KDJ_K_OVERSOLD': 20,
    'SWING_KDJ_K_OVERBOUGHT': 80,
    'SWING_VOLUME_MA_PERIOD': 20,
    'SWING_VOLUME_SPIKE_RATIO': 1.5,
    'SWING_BUY_SIGNAL_THRESHOLD': 3,
    'SWING_SELL_SIGNAL_THRESHOLD': 3,
    'SWING_TREND_PERIOD': 10,
    'SWING_TREND_SLOPE_THRESHOLD': 0.0008,
    'SWING_TREND_BUY_BOOST': 1,
    'SWING_TREND_SELL_SUPPRESS': 1,
    'SWING_TREND_SELL_BOOST': 1,
    'SWING_TREND_BUY_SUPPRESS': 1,
    'SWING_BUY_COOLDOWN': 120,
    'SWING_SELL_COOLDOWN': 120,
    'SWING_MAX_DAILY_BUYS': 3,
    'SWING_MAX_DAILY_SELLS': 3,
    'SWING_BUY_AMOUNT': 15000,
    'SWING_SELL_AMOUNT': 15000,
    'SWING_MAX_HOLDINGS': 5,
    'SWING_MIN_BUY_VOLUME': 100,
    'SWING_MIN_SELL_VOLUME': 100,
    'SWING_MIN_PROFIT_RATIO': 0.01,
    'SWING_STOP_LOSS_ENABLED': True,
    'SWING_STOP_LOSS_RATIO': -0.03,
    'SWING_CONSECUTIVE_FAILURE_LIMIT': 3,
    'SWING_FAILURE_COOLDOWN': 300,
    'BASE_VOLUME': 1000,
    'ENABLE_INDEX_FILTER': False,
    'ENABLE_1M_CONFIRMATION': True,
    # ===== P0: 多时间框架 + 移动止盈 =====
    'MTF_DAILY_TREND': '',          # ''=auto从数据推断, 'up'/'down'/'range'=手动指定
    'MTF_30M_TREND': '',
    'MTF_STRICT_MODE': False,
    'TRAILING_STOP_ENABLED': True,
    'TRAILING_STOP_ACTIVATION': 0.03,
    'TRAILING_STOP_BREAKEVEN': 0.02,
    'TRAILING_STOP_DISTANCE': 0.02,
    # ===== P1: ATR仓位 + VWAP + 动态冷却 =====
    'ATR_POSITION_ADAPTIVE': True,
    'ATR_POSITION_REFERENCE': 0.025,
    'ATR_POSITION_MIN_RATIO': 0.5,
    'ATR_POSITION_MAX_RATIO': 1.5,
    'USE_VWAP': True,
    'VWAP_BOOST': 1,
    'VWAP_ABOVE_PENALTY': 1,
    'VWAP_BELOW_PENALTY': 1,
    'COOLDOWN_DYNAMIC': True,
    'COOLDOWN_TREND_MULT': 0.5,
    'COOLDOWN_RANGE_MULT': 1.5,
    # ===== P2: ADX + 背离 + 滑点 =====
    'USE_ADX': True,
    'ADX_PERIOD': 14,
    'ADX_MIN_THRESHOLD': 18,
    'ADX_STRONG_THRESHOLD': 40,
    'USE_HIDDEN_DIVERGENCE': True,
    'HIDDEN_DIVERGENCE_BOOST': 2,
    'USE_TRIPLE_DIVERGENCE': True,
    'DIVERGENCE_LOOKBACK': 5,
    'SLIPPAGE_BPS': 5.0,            # 滑点（基点），0=无滑点
    'SLIPPAGE_MIN_TICK': 0.01,      # 最小跳价
}


def load_csv(path):
    """加载录制的5分钟K线CSV"""
    df = pd.read_csv(path)
    required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV缺少必要列: {missing}")
    for c in ['open', 'high', 'low', 'close']:
        df[c] = df[c].astype(float)
    df['volume'] = df['volume'].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


# ============ P2: Pivot / 背离 / ADX / VWAP 离线计算 ============

def _find_pivot_highs(close, lookback=5):
    n = len(close)
    pivots = []
    for i in range(lookback, n - lookback):
        left = close[i-lookback:i]
        right = close[i+1:i+lookback+1]
        if all(close[i] >= x for x in left) and all(close[i] >= x for x in right):
            pivots.append({'price': float(close[i]), 'idx': i})
    return pivots

def _find_pivot_lows(close, lookback=5):
    n = len(close)
    pivots = []
    for i in range(lookback, n - lookback):
        left = close[i-lookback:i]
        right = close[i+1:i+lookback+1]
        if all(close[i] <= x for x in left) and all(close[i] <= x for x in right):
            pivots.append({'price': float(close[i]), 'idx': i})
    return pivots

def _detect_hidden_bearish(close, rsi, lookback=5):
    pivots = _find_pivot_highs(close, lookback)
    if len(pivots) < 2: return False
    prev, last = pivots[-2], pivots[-1]
    return last['price'] < prev['price'] and rsi[last['idx']] > rsi[prev['idx']]

def _detect_hidden_bullish(close, rsi, lookback=5):
    pivots = _find_pivot_lows(close, lookback)
    if len(pivots) < 2: return False
    prev, last = pivots[-2], pivots[-1]
    return last['price'] > prev['price'] and rsi[last['idx']] < rsi[prev['idx']]

def _detect_triple_bearish(close, rsi, lookback=5):
    pivots = _find_pivot_highs(close, lookback)
    if len(pivots) < 3: return False
    p1, p2, p3 = pivots[-3], pivots[-2], pivots[-1]
    return p3['price'] < p2['price'] < p1['price'] and \
        float(rsi[p3['idx']]) < float(rsi[p2['idx']]) < float(rsi[p1['idx']])

def _detect_triple_bullish(close, rsi, lookback=5):
    pivots = _find_pivot_lows(close, lookback)
    if len(pivots) < 3: return False
    p1, p2, p3 = pivots[-3], pivots[-2], pivots[-1]
    return p3['price'] > p2['price'] > p1['price'] and \
        float(rsi[p3['idx']]) > float(rsi[p2['idx']]) > float(rsi[p1['idx']])

def _detect_bearish(close, rsi, macd_hist, lookback=5):
    pivots = _find_pivot_highs(close, lookback)
    if len(pivots) < 2: return False
    prev, last = pivots[-2], pivots[-1]
    return last['price'] > prev['price'] and \
        rsi[last['idx']] < rsi[prev['idx']] and \
        macd_hist[last['idx']] < macd_hist[prev['idx']]

def _detect_structure(close, lookback=5):
    """简化版市场结构检测：识别最近一次 HH/HL/LH/LL 转折"""
    if len(close) < lookback * 4:
        return {'trend': 'range', 'new_swing': None}
    # 找最近两个 swing 点
    pivots_high = _find_pivot_highs(close, lookback)
    pivots_low = _find_pivot_lows(close, lookback)
    result = {'trend': 'range', 'new_swing': None}
    if len(pivots_high) >= 2 and len(pivots_low) >= 2:
        h1, h0 = pivots_high[-2], pivots_high[-1]
        l1, l0 = pivots_low[-2], pivots_low[-1]
        if h0['price'] > h1['price'] and l0['price'] > l1['price']:
            result['trend'] = 'up'
            result['new_swing'] = 'HL' if h0['idx'] < l0['idx'] else 'HH'
        elif h0['price'] < h1['price'] and l0['price'] < l1['price']:
            result['trend'] = 'down'
            result['new_swing'] = 'LH' if h0['idx'] < l0['idx'] else 'LL'
        elif h0['idx'] > l0['idx'] and h0['price'] > h1['price'] and l0['idx'] < h0['idx']:
            result['new_swing'] = 'HL'
        elif l0['idx'] > h0['idx'] and l0['price'] < l1['price'] and h0['idx'] < l0['idx']:
            result['new_swing'] = 'LH'
    return result

def _detect_bullish(close, rsi, macd_hist, lookback=5):
    pivots = _find_pivot_lows(close, lookback)
    if len(pivots) < 2: return False
    prev, last = pivots[-2], pivots[-1]
    return last['price'] < prev['price'] and \
        rsi[last['idx']] > rsi[prev['idx']] and \
        macd_hist[last['idx']] > macd_hist[prev['idx']]

def _calc_adx(high, low, close, period=14):
    n = len(close)
    if n < period + 1:
        return np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    tr = np.zeros(n); plus_dm = np.zeros(n); minus_dm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        up_move = high[i] - high[i-1]; down_move = low[i-1] - low[i]
        if up_move > down_move and up_move > 0: plus_dm[i] = up_move
        if down_move > up_move and down_move > 0: minus_dm[i] = down_move
    alpha = 1.0 / period
    atr = np.zeros(n); atr[period] = np.mean(tr[1:period+1])
    for i in range(period + 1, n): atr[i] = atr[i-1] + alpha * (tr[i] - atr[i-1])
    sp = np.zeros(n); sm = np.zeros(n)
    sp[period] = np.sum(plus_dm[1:period+1]); sm[period] = np.sum(minus_dm[1:period+1])
    for i in range(period + 1, n):
        sp[i] = sp[i-1] + alpha * (plus_dm[i] - sp[i-1])
        sm[i] = sm[i-1] + alpha * (minus_dm[i] - sm[i-1])
    pdi = np.full(n, np.nan); mdi = np.full(n, np.nan)
    dx = np.full(n, np.nan); adx = np.full(n, np.nan)
    for i in range(period, n):
        if atr[i] > 0:
            pdi[i] = 100.0 * sp[i] / atr[i]; mdi[i] = 100.0 * sm[i] / atr[i]
            if pdi[i] + mdi[i] > 0: dx[i] = 100.0 * abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i])
    if n > period * 2:
        adx[period*2-1] = np.mean(dx[period:period*2])
        for i in range(period*2, n): adx[i] = adx[i-1] + alpha * (dx[i] - adx[i-1])
    return adx, pdi, mdi

def _calc_vwap(high, low, close, volume):
    tp = (high + low + close) / 3.0
    cum_pv = np.cumsum(tp * volume); cum_vol = np.cumsum(volume)
    vwap = np.full(len(close), np.nan)
    mask = cum_vol > 0; vwap[mask] = cum_pv[mask] / cum_vol[mask]
    return vwap

# ============ P1: 滑点模型 ============

def apply_slippage(price, direction, volume, slippage_bps=5.0, min_tick=0.01):
    """买入加滑点（实际成交价更高），卖出减滑点（实际成交价更低）"""
    if slippage_bps <= 0: return price
    slip = price * slippage_bps / 15000.0
    slip = max(slip, min_tick)
    if direction == 'buy': return price + slip
    else: return price - slip

def calc_indicators(close, open_, high, low, volume, params, close_1m_arr=None):
    """计算全部摆动指标，返回与 calculate_intraday_indicators 相同结构的 dict"""
    n = len(close)
    min_len = max(params['SWING_BOLL_PERIOD'], params['SWING_RSI_PERIOD'],
                  params['SWING_MACD_SLOW'] + params['SWING_MACD_SIGNAL'],
                  params['SWING_KDJ_PERIOD'] + 3)
    if n < min_len:
        return None

    upper, mid, lower = BOLL(close, N=params['SWING_BOLL_PERIOD'], P=params['SWING_BOLL_STD'])
    rsi_series = RSI(close, N=params['SWING_RSI_PERIOD'])
    dif, dea, hist = MACD(close, SHORT=params['SWING_MACD_FAST'],
                          LONG=params['SWING_MACD_SLOW'], M=params['SWING_MACD_SIGNAL'])
    vol_ma = MA(volume, N=params['SWING_VOLUME_MA_PERIOD'])
    k, d, j = KDJ(close, high, low, N=params['SWING_KDJ_PERIOD'], M1=3, M2=3)

    # 趋势斜率
    trend_slope = 0.0
    trend_n = params['SWING_TREND_PERIOD']
    if n >= trend_n:
        recent = close[-trend_n:]
        x = np.arange(trend_n)
        slope_val = (trend_n * np.sum(x * recent) - np.sum(x) * np.sum(recent)) / \
                    (trend_n * np.sum(x ** 2) - np.sum(x) ** 2)
        avg = np.mean(recent)
        if avg > 0:
            trend_slope = float(slope_val / avg)

    prev_close = float(close[-2]) if n >= 2 else float(close[-1])

    # 1分钟线快周期指标
    close_1m = float(close[-1])
    rsi_1m = float(rsi_series[-1])
    macd_hist_1m = float(hist[-1])
    prev_macd_hist_1m = float(hist[-2]) if len(hist) >= 2 else 0.0
    if close_1m_arr is not None and len(close_1m_arr) >= 20:
        c1 = close_1m_arr
        close_1m = float(c1[-1])
        r1 = RSI(c1, N=min(14, len(c1) - 2))
        rsi_1m = float(r1[-1]) if len(r1) > 0 else 50.0
        _, _, h1 = MACD(c1, SHORT=6, LONG=13, M=5)
        macd_hist_1m = float(h1[-1]) if len(h1) > 0 else 0.0
        prev_macd_hist_1m = float(h1[-2]) if len(h1) >= 2 else 0.0

    # P2: ADX / P1: VWAP
    lookback = params.get('DIVERGENCE_LOOKBACK', 5)
    adx_vals, pdi_vals, mdi_vals = _calc_adx(high, low, close, params.get('ADX_PERIOD', 14))
    vwap_vals = _calc_vwap(high, low, close, volume)

    return {
        'close': float(close[-1]),
        'open': float(open_[-1]),
        'high': float(high[-1]),
        'low': float(low[-1]),
        'prev_close': prev_close,
        'boll_upper': float(upper[-1]),
        'boll_mid': float(mid[-1]),
        'boll_lower': float(lower[-1]),
        'rsi': float(rsi_series[-1]),
        'macd': float(dif[-1]),
        'macd_signal': float(dea[-1]),
        'macd_hist': float(hist[-1]),
        'volume': float(volume[-1]),
        'volume_ma': float(vol_ma[-1]),
        'kdj_k': float(k[-1]),
        'kdj_d': float(d[-1]),
        'kdj_j': float(j[-1]),
        'prev_macd_hist': float(hist[-2]) if len(hist) >= 2 else 0.0,
        'prev_rsi': float(rsi_series[-2]) if len(rsi_series) >= 2 else 50.0,
        'prev_kdj_k': float(k[-2]) if len(k) >= 2 else 50.0,
        'prev_kdj_d': float(d[-2]) if len(d) >= 2 else 50.0,
        'trend_slope': trend_slope,
        'atr': float(sum(high[-14:]-low[-14:])/14/close[-1]) if len(close) >= 14 else 0.02,
        # 1分钟快周期
        'close_1m': close_1m,
        'rsi_1m': rsi_1m,
        'macd_hist_1m': macd_hist_1m,
        'prev_macd_hist_1m': prev_macd_hist_1m,
        # P2: 背离（标准+隐藏+3重）
        'div_bullish': _detect_bullish(close, rsi_series, hist, lookback),
        'div_bearish': _detect_bearish(close, rsi_series, hist, lookback),
        'div_hidden_bullish': _detect_hidden_bullish(close, rsi_series, lookback) if params.get('USE_HIDDEN_DIVERGENCE', True) else False,
        'div_hidden_bearish': _detect_hidden_bearish(close, rsi_series, lookback) if params.get('USE_HIDDEN_DIVERGENCE', True) else False,
        'div_triple_bullish': _detect_triple_bullish(close, rsi_series, lookback) if params.get('USE_TRIPLE_DIVERGENCE', True) else False,
        'div_triple_bearish': _detect_triple_bearish(close, rsi_series, lookback) if params.get('USE_TRIPLE_DIVERGENCE', True) else False,
        # P2: ADX
        'adx': float(adx_vals[-1]) if not np.isnan(adx_vals[-1]) else 20.0,
        'plus_di': float(pdi_vals[-1]) if not np.isnan(pdi_vals[-1]) else 0.0,
        'minus_di': float(mdi_vals[-1]) if not np.isnan(mdi_vals[-1]) else 0.0,
        # P1: VWAP
        'vwap': float(vwap_vals[-1]) if not np.isnan(vwap_vals[-1]) else float(close[-1]),
        # 市场结构（简化版：5-bar pivot检测 HH/HL/LH/LL）
        'structure': _detect_structure(close),
    }


def score_buy(indicators, params):
    """买入信号打分（与 swing_trading_manager._score_buy_signal 一致）"""
    score, details = 0, []
    price, rsi = indicators['close'], indicators['rsi']
    macd_hist, prev_macd = indicators['macd_hist'], indicators['prev_macd_hist']
    vol, vol_ma = indicators['volume'], indicators['volume_ma']
    boll_lower = indicators['boll_lower']

    if boll_lower > 0 and price <= boll_lower * 1.005:
        score += 2; details.append(f"触及下轨({price:.2f}<={boll_lower:.2f})")
    # 底背离：pivot价格新低，RSI拒绝新低
    if indicators.get('div_bullish', False):
        score += 2; details.append("RSI底背离(pivot确认)")
    if rsi < params['SWING_RSI_OVERSOLD']:
        score += 2; details.append(f"RSI超卖({rsi:.1f}<{params['SWING_RSI_OVERSOLD']})")
    if rsi < params['SWING_RSI_OVERSOLD'] - 5:
        score += 1; details.append(f"RSI深度超卖({rsi:.1f})")
    if macd_hist > 0 and prev_macd < 0:
        score += 2; details.append("MACD金叉")
    if macd_hist > 0:
        score += 1; details.append("MACD柱>0")
    if vol_ma > 0 and vol > vol_ma * params['SWING_VOLUME_SPIKE_RATIO']:
        score += 1; details.append("放量确认")

    k, d, j = indicators['kdj_k'], indicators['kdj_d'], indicators['kdj_j']
    pk, pd = indicators['prev_kdj_k'], indicators['prev_kdj_d']
    if pk <= pd and k > d:
        if k < params['SWING_KDJ_K_OVERSOLD']:
            score += 2; details.append(f"KDJ低位金叉(K={k:.1f})")
        else:
            score += 1; details.append(f"KDJ金叉(K={k:.1f})")
    if j < 0:
        score += 1; details.append(f"KDJ-J超卖(J={j:.1f})")
    if k < params['SWING_KDJ_K_OVERSOLD'] and d < params['SWING_KDJ_K_OVERSOLD']:
        score += 1; details.append(f"KDJ超卖区(K={k:.1f},D={d:.1f})")

    # P2: 隐藏底背离
    if params.get('USE_HIDDEN_DIVERGENCE', True) and indicators.get('div_hidden_bullish', False):
        score += params.get('HIDDEN_DIVERGENCE_BOOST', 2); details.append("隐藏底背离")
    # P2: 3重底背离
    if params.get('USE_TRIPLE_DIVERGENCE', True) and indicators.get('div_triple_bullish', False):
        score += 3; details.append("3重底背离(强反转)")

    # P1: VWAP评分
    if params.get('USE_VWAP', True):
        vwap = indicators.get('vwap', 0); price = indicators.get('close_1m', indicators['close'])
        if vwap > 0:
            if price < vwap: score += params.get('VWAP_BOOST', 1); details.append(f"VWAP下方")
            else: score -= params.get('VWAP_ABOVE_PENALTY', 1); details.append(f"VWAP上方")

    # 1分钟线确认
    if params.get('ENABLE_1M_CONFIRMATION', True):
        rsi_1m = indicators.get('rsi_1m', 50)
        m1m = indicators.get('macd_hist_1m', 0)
        m1m_prev = indicators.get('prev_macd_hist_1m', 0)
        if rsi_1m < params['SWING_RSI_OVERSOLD']:
            score += 1; details.append(f"1m-RSI超卖确认({rsi_1m:.1f})")
        if m1m > m1m_prev and m1m > -0.005:
            score += 1; details.append("1m-MACD上行确认")
        elif m1m < m1m_prev and m1m < -0.01:
            score -= 1; details.append("1m-MACD仍在下跌(逆风)")

    return score, details


def score_sell(indicators, params):
    """卖出信号打分"""
    score, details = 0, []
    price, rsi = indicators['close'], indicators['rsi']
    macd_hist, prev_macd = indicators['macd_hist'], indicators['prev_macd_hist']
    vol, vol_ma = indicators['volume'], indicators['volume_ma']
    boll_upper = indicators['boll_upper']

    if boll_upper > 0 and price >= boll_upper * 0.995:
        score += 2; details.append(f"触及上轨({price:.2f}>={boll_upper:.2f})")
    # 顶背离：pivot价格新高，RSI拒绝新高
    if indicators.get('div_bearish', False):
        score += 2; details.append("RSI顶背离(pivot确认)")
    if rsi > params['SWING_RSI_OVERBOUGHT']:
        score += 2; details.append(f"RSI超买({rsi:.1f}>{params['SWING_RSI_OVERBOUGHT']})")
    if rsi > params['SWING_RSI_OVERBOUGHT'] + 5:
        score += 1; details.append(f"RSI深度超买({rsi:.1f})")
    if macd_hist < 0 and prev_macd > 0:
        score += 2; details.append("MACD死叉")
    if macd_hist < 0:
        score += 1; details.append("MACD柱<0")
    if vol_ma > 0 and vol > vol_ma * params['SWING_VOLUME_SPIKE_RATIO']:
        score += 1; details.append("放量确认")

    k, d, j = indicators['kdj_k'], indicators['kdj_d'], indicators['kdj_j']
    pk, pd = indicators['prev_kdj_k'], indicators['prev_kdj_d']
    if pk >= pd and k < d:
        if k > params['SWING_KDJ_K_OVERBOUGHT']:
            score += 2; details.append(f"KDJ高位死叉(K={k:.1f})")
        else:
            score += 1; details.append(f"KDJ死叉(K={k:.1f})")
    if j > 100:
        score += 1; details.append(f"KDJ-J超买(J={j:.1f})")
    if k > params['SWING_KDJ_K_OVERBOUGHT'] and d > params['SWING_KDJ_K_OVERBOUGHT']:
        score += 1; details.append(f"KDJ超买区(K={k:.1f},D={d:.1f})")

    # P2: 隐藏顶背离
    if params.get('USE_HIDDEN_DIVERGENCE', True) and indicators.get('div_hidden_bearish', False):
        score += params.get('HIDDEN_DIVERGENCE_BOOST', 2); details.append("隐藏顶背离")
    # P2: 3重顶背离
    if params.get('USE_TRIPLE_DIVERGENCE', True) and indicators.get('div_triple_bearish', False):
        score += 3; details.append("3重顶背离(强反转)")

    # P1: VWAP评分
    if params.get('USE_VWAP', True):
        vwap = indicators.get('vwap', 0); price = indicators.get('close_1m', indicators['close'])
        if vwap > 0:
            if price > vwap: score += params.get('VWAP_BOOST', 1); details.append(f"VWAP上方")
            else: score -= params.get('VWAP_BELOW_PENALTY', 1); details.append(f"VWAP下方")

    # 1分钟线确认
    if params.get('ENABLE_1M_CONFIRMATION', True):
        rsi_1m = indicators.get('rsi_1m', 50)
        m1m = indicators.get('macd_hist_1m', 0)
        m1m_prev = indicators.get('prev_macd_hist_1m', 0)
        if rsi_1m > params['SWING_RSI_OVERBOUGHT']:
            score += 1; details.append(f"1m-RSI超买确认({rsi_1m:.1f})")
        if m1m < m1m_prev and m1m < 0.005:
            score += 1; details.append("1m-MACD下行确认")
        elif m1m > m1m_prev and m1m > 0.01:
            score -= 1; details.append("1m-MACD仍在上涨(惜售)")

    return score, details


def is_freefall(indicators):
    """急跌检测"""
    close = indicators.get('close', 0)
    open_p = indicators.get('open', 0)
    prev_close = indicators.get('prev_close', 0)
    if close <= 0 or open_p <= 0:
        return False
    bar_change = (close - open_p) / open_p
    if bar_change > -0.01:
        return False
    if prev_close > 0 and open_p > 0:
        prev_bar_change = (open_p - prev_close) / prev_close
        if prev_bar_change < -0.005:
            return True
    if bar_change < -0.02:
        return True
    return False


def get_effective_thresholds(trend_slope, params):
    """趋势自适应阈值"""
    slope, threshold = trend_slope, params['SWING_TREND_SLOPE_THRESHOLD']
    if slope > threshold:
        trend = 'up'
        buy_th = params['SWING_BUY_SIGNAL_THRESHOLD'] - params['SWING_TREND_BUY_BOOST']
        sell_th = params['SWING_SELL_SIGNAL_THRESHOLD'] + params['SWING_TREND_SELL_SUPPRESS']
    elif slope < -threshold:
        trend = 'down'
        buy_th = params['SWING_BUY_SIGNAL_THRESHOLD'] + params['SWING_TREND_BUY_SUPPRESS']
        sell_th = params['SWING_SELL_SIGNAL_THRESHOLD'] - params['SWING_TREND_SELL_BOOST']
    else:
        trend = 'range'
        buy_th = params['SWING_BUY_SIGNAL_THRESHOLD']
        sell_th = params['SWING_SELL_SIGNAL_THRESHOLD']
    return trend, buy_th, sell_th


def replay(path, params, verbose=True, path_1m=None):
    """逐K线回放摆动交易逻辑，返回交易记录和摘要"""
    df = load_csv(path)
    df_1m = load_csv(path_1m) if path_1m else None
    base_volume = params['BASE_VOLUME']
    n = len(df)

    # 状态变量
    floating_volume = 0
    today_buy_count, today_sell_count = 0, 0
    today_buy_volume, today_sell_volume = 0, 0
    last_buy_bar, last_sell_bar = -9999, -9999
    consecutive_failures = 0
    failure_until_bar = -1
    swing_entry_price = 0.0

    trades = []
    bar_log = []

    min_bars = max(params['SWING_BOLL_PERIOD'], params['SWING_RSI_PERIOD'],
                   params['SWING_MACD_SLOW'] + params['SWING_MACD_SIGNAL'],
                   params['SWING_KDJ_PERIOD'] + 3)

    sellable_base = base_volume  # 实盘模式T+1

    for i in range(min_bars, n):
        window = df.iloc[:i + 1]
        c = window['close'].values
        o = window['open'].values
        h = window['high'].values
        l = window['low'].values
        v = window['volume'].values
        ts = df.iloc[i]['timestamp']

        # 获取对应时间点的1分钟K线
        c1_arr = None
        if df_1m is not None:
            bar_ts = pd.Timestamp(ts)
            window_1m = df_1m[df_1m['timestamp'] <= bar_ts]
            if len(window_1m) >= 20:
                c1_arr = window_1m['close'].values

        ind = calc_indicators(c, o, h, l, v, params, close_1m_arr=c1_arr)
        if ind is None:
            continue

        b_score, b_det = score_buy(ind, params)
        s_score, s_det = score_sell(ind, params)

        # 市场结构信号加权（与实盘一致：HL +3买入分, LH +3卖出分）
        structure = ind.get('structure', {})
        new_swing = structure.get('new_swing') if structure else None
        if new_swing == 'HL':
            b_score += 3; b_det.append('5m结构HL')
        if new_swing == 'LH':
            s_score += 3; s_det.append('5m结构LH')

        trend, buy_th, sell_th = get_effective_thresholds(ind['trend_slope'], params)
        price = ind.get('close_1m', ind['close'])

        log_entry = {
            'bar': i, 'timestamp': ts, 'price': price,
            'buy_score': b_score, 'buy_threshold': buy_th,
            'sell_score': s_score, 'sell_threshold': sell_th,
            'trend': trend, 'slope': f"{ind['trend_slope']:.6f}",
            'rsi': f"{ind['rsi']:.1f}",
            'buy_detail': '; '.join(b_det) if b_det else '-',
            'sell_detail': '; '.join(s_det) if s_det else '-',
            'action': '-',
        }

        # 连续失败冷却
        if i < failure_until_bar:
            bar_log.append(log_entry)
            continue

        # P2: ADX 趋势强度过滤（无趋势震荡不交易）
        if params.get('USE_ADX', True):
            adx_val = ind.get('adx', 20)
            if adx_val < params.get('ADX_MIN_THRESHOLD', 18):
                bar_log.append(log_entry)
                continue

        # 摆动独立止损检查（优先于信号检测）
        if params.get('SWING_STOP_LOSS_ENABLED', True) and swing_entry_price > 0:
            stop_loss_ratio = params.get('SWING_STOP_LOSS_RATIO', -0.03)
            if price < swing_entry_price * (1 + stop_loss_ratio):
                sell_vol = int(params['SWING_SELL_AMOUNT'] / price / 100) * 100 + 100
                if sell_vol < params['SWING_MIN_SELL_VOLUME']:
                    sell_vol = params['SWING_MIN_SELL_VOLUME']
                if sell_vol >= params['SWING_MIN_SELL_VOLUME']:
                    exec_price = apply_slippage(price, 'sell', sell_vol,
                                                params.get('SLIPPAGE_BPS', 5.0))
                    trades.append({'bar': i, 'timestamp': ts, 'direction': 'SELL',
                                   'price': exec_price, 'volume': sell_vol,
                                   'amount': exec_price * sell_vol, 'confidence': 0,
                                   'tag': '固定止损'})
                    log_entry['action'] = f'STOP {sell_vol}股 @ {exec_price:.2f}'
                    today_sell_count += 1
                    today_sell_volume += sell_vol
                    last_sell_bar = i
                    swing_entry_price = 0.0
                    consecutive_failures = 0
                    bar_log.append(log_entry)
                    continue

        # P0: 移动止盈/追踪止损检查
        trailing_high = getattr(replay, '_trailing_high', {})
        if params.get('TRAILING_STOP_ENABLED', True) and swing_entry_price > 0:
            profit = (price - swing_entry_price) / swing_entry_price
            prev_high = trailing_high.get('peak', swing_entry_price)
            trailing_high['peak'] = max(prev_high, price)
            peak = trailing_high['peak']
            activation = params.get('TRAILING_STOP_ACTIVATION', 0.03)
            breakeven = params.get('TRAILING_STOP_BREAKEVEN', 0.02)
            distance = params.get('TRAILING_STOP_DISTANCE', 0.02)
            triggered = False
            if profit >= breakeven and price <= swing_entry_price:
                triggered = True  # 保本损
            elif profit >= activation:
                stop_price = peak * (1 - distance)
                if price <= stop_price:
                    triggered = True  # 追踪止损
            if triggered:
                sell_vol = int(params['SWING_SELL_AMOUNT'] / price / 100) * 100 + 100
                if sell_vol < params['SWING_MIN_SELL_VOLUME']:
                    sell_vol = params['SWING_MIN_SELL_VOLUME']
                if sell_vol >= params['SWING_MIN_SELL_VOLUME']:
                    exec_price = apply_slippage(price, 'sell', sell_vol,
                                                params.get('SLIPPAGE_BPS', 5.0))
                    tag = f'追踪止盈(最高{peak:.2f})' if profit >= activation else '保本止盈'
                    trades.append({'bar': i, 'timestamp': ts, 'direction': 'SELL',
                                   'price': exec_price, 'volume': sell_vol,
                                   'amount': exec_price * sell_vol, 'confidence': 0,
                                   'tag': tag})
                    log_entry['action'] = f'TRAIL {sell_vol}股 @ {exec_price:.2f}'
                    today_sell_count += 1
                    today_sell_volume += sell_vol
                    last_sell_bar = i
                    swing_entry_price = 0.0
                    trailing_high['peak'] = 0
                    consecutive_failures = 0
                    bar_log.append(log_entry)
                    continue
        replay._trailing_high = trailing_high

        # P1: 动态冷却（bar数近似）
        def _dynamic_cooldown_bars(base_seconds, trend, adx_val):
            if not params.get('COOLDOWN_DYNAMIC', True):
                return max(1, base_seconds // 300)
            if adx_val > params.get('ADX_STRONG_THRESHOLD', 40):
                mult = 0.3
            elif trend in ('up', 'down'):
                mult = params.get('COOLDOWN_TREND_MULT', 0.5)
            else:
                mult = params.get('COOLDOWN_RANGE_MULT', 1.5)
            return max(1, int(base_seconds * mult / 300))

        # 尝试买入信号
        if b_score >= buy_th and not is_freefall(ind):
            buy_cd_bars = _dynamic_cooldown_bars(params['SWING_BUY_COOLDOWN'], trend, ind.get('adx', 20))
            if (today_buy_count < params['SWING_MAX_DAILY_BUYS']
                    and i - last_buy_bar >= buy_cd_bars):
                # 固定金额 → 向上取整到100股
                buy_vol = int(params['SWING_BUY_AMOUNT'] / price / 100) * 100 + 100
                if buy_vol < params['SWING_MIN_BUY_VOLUME']:
                    buy_vol = params['SWING_MIN_BUY_VOLUME']

                if buy_vol >= params['SWING_MIN_BUY_VOLUME']:
                    exec_price = apply_slippage(price, 'buy', buy_vol,
                                                params.get('SLIPPAGE_BPS', 5.0))
                    if swing_entry_price > 0 and today_buy_volume > 0:
                        swing_entry_price = ((swing_entry_price * today_buy_volume + buy_vol * exec_price)
                                             / (today_buy_volume + buy_vol))
                    else:
                        swing_entry_price = exec_price
                    floating_volume += buy_vol
                    today_buy_count += 1
                    today_buy_volume += buy_vol
                    last_buy_bar = i
                    consecutive_failures = 0
                    trades.append({'bar': i, 'timestamp': ts, 'direction': 'BUY',
                                   'price': exec_price, 'volume': buy_vol,
                                   'amount': exec_price * buy_vol, 'confidence': b_score,
                                   'tag': f'买入(滑点{exec_price-price:+.3f})' if abs(exec_price-price) > 0.001 else '买入'})
                    log_entry['action'] = f'BUY {buy_vol}股 @ {exec_price:.2f}'
                else:
                    consecutive_failures += 1
            else:
                pass  # 冷却或达到上限

        # 尝试卖出信号
        elif s_score >= sell_th:
            sell_cd_bars = _dynamic_cooldown_bars(params['SWING_SELL_COOLDOWN'], trend, ind.get('adx', 20))
            sellable_base_current = base_volume + today_buy_volume - today_sell_volume
            if (today_sell_count < params['SWING_MAX_DAILY_SELLS']
                    and i - last_sell_bar >= sell_cd_bars):
                sell_vol = int(params['SWING_SELL_AMOUNT'] / price / 100) * 100 + 100
                if sell_vol < params['SWING_MIN_SELL_VOLUME']:
                    sell_vol = params['SWING_MIN_SELL_VOLUME']
                sell_vol = min(sell_vol, sellable_base_current)

                # 最小盈利检查
                entry = swing_entry_price if swing_entry_price > 0 else float(c[min_bars])
                if entry > 0 and price < entry * (1 + params['SWING_MIN_PROFIT_RATIO']):
                    bar_log.append(log_entry)
                    continue

                if sell_vol >= params['SWING_MIN_SELL_VOLUME']:
                    exec_price = apply_slippage(price, 'sell', sell_vol,
                                                params.get('SLIPPAGE_BPS', 5.0))
                    today_sell_count += 1
                    today_sell_volume += sell_vol
                    last_sell_bar = i
                    consecutive_failures = 0
                    if sell_vol >= sell_vol * 0.8:
                        swing_entry_price = 0.0
                    profit_tag = f'+{(exec_price-entry)/entry*100:.2f}%' if entry > 0 else ''
                    trades.append({'bar': i, 'timestamp': ts, 'direction': 'SELL',
                                   'price': exec_price, 'volume': sell_vol,
                                   'amount': exec_price * sell_vol, 'confidence': s_score,
                                   'tag': f'卖出{profit_tag}'})
                    log_entry['action'] = f'SELL {sell_vol}股 @ {exec_price:.2f}'
                else:
                    consecutive_failures += 1
            else:
                pass

        # 连续失败保护
        if consecutive_failures >= params['SWING_CONSECUTIVE_FAILURE_LIMIT']:
            failure_until_bar = i + max(1, params['SWING_FAILURE_COOLDOWN'] // 300)
            consecutive_failures = 0

        bar_log.append(log_entry)

    return bar_log, trades, df


def print_report(bar_log, trades, df, params):
    """打印回放报告"""
    stock_code = os.path.basename(df.iloc[0].get('stock_code', '')) if 'stock_code' in df.columns else ''
    print(f"\n{'='*80}")
    print(f"  摆动交易离线回放报告")
    print(f"{'='*80}")
    print(f"  数据文件: {len(df)} 根K线 | {df.iloc[0]['timestamp']} ~ {df.iloc[-1]['timestamp']}")
    print(f"  底仓: {params['BASE_VOLUME']}股")
    print(f"  买入阈值: {params['SWING_BUY_SIGNAL_THRESHOLD']} | 卖出阈值: {params['SWING_SELL_SIGNAL_THRESHOLD']}")
    print(f"  买入冷却: {params['SWING_BUY_COOLDOWN']}s | 卖出冷却: {params['SWING_SELL_COOLDOWN']}s")
    print(f"  单日最大: 买{params['SWING_MAX_DAILY_BUYS']}次 | 卖{params['SWING_MAX_DAILY_SELLS']}次")
    print(f"  买入金额: {params['SWING_BUY_AMOUNT']:,} | 卖出金额: {params['SWING_SELL_AMOUNT']:,}")
    features_on = []
    if params.get('TRAILING_STOP_ENABLED', True): features_on.append('移动止盈')
    if params.get('USE_VWAP', True): features_on.append('VWAP')
    if params.get('USE_ADX', True): features_on.append('ADX')
    if params.get('ATR_POSITION_ADAPTIVE', True): features_on.append('ATR仓位')
    if params.get('COOLDOWN_DYNAMIC', True): features_on.append('动态冷却')
    if params.get('USE_HIDDEN_DIVERGENCE', True): features_on.append('隐藏背离')
    if params.get('USE_TRIPLE_DIVERGENCE', True): features_on.append('3重背离')
    features_off = []
    if not params.get('TRAILING_STOP_ENABLED', True): features_off.append('移动止盈')
    if not params.get('USE_VWAP', True): features_off.append('VWAP')
    if not params.get('USE_ADX', True): features_off.append('ADX')
    print(f"  已启用: {', '.join(features_on) if features_on else '无'}")
    if features_off: print(f"  已关闭: {', '.join(features_off)}")
    print(f"  滑点: {params.get('SLIPPAGE_BPS', 5.0)}bps")

    if not trades:
        print(f"\n  ⚠ 无任何交易信号触发")
        # 打印最高分K线供参考
        max_buy = max(bar_log, key=lambda x: x['buy_score'])
        max_sell = max(bar_log, key=lambda x: x['sell_score'])
        print(f"  最高买入分: {max_buy['buy_score']} @ {max_buy['timestamp']} "
              f"价格={max_buy['price']:.2f} [{max_buy['buy_detail']}]")
        print(f"  最高卖出分: {max_sell['sell_score']} @ {max_sell['timestamp']} "
              f"价格={max_sell['price']:.2f} [{max_sell['sell_detail']}]")
        return

    print(f"\n  {'─'*86}")
    print(f"  {'时间':<18} {'方向':<6} {'价格':>8} {'数量':>8} {'金额':>10} {'分':>4} {'说明'}")
    print(f"  {'─'*86}")
    total_buy_amt = 0
    total_sell_amt = 0
    for t in trades:
        direction = t['direction']
        tag = t.get('tag', '')
        print(f"  {t['timestamp']:<18} {direction:<6} {t['price']:>8.2f} {t['volume']:>8} {t['amount']:>10.0f} {t['confidence']:>4} {tag}")
        if direction == 'BUY':
            total_buy_amt += t['amount']
        else:
            total_sell_amt += t['amount']
    print(f"  {'─'*86}")

    # 绩效归因（必须在 FIFO 盈亏之前算，避免 trades 被修改）
    bv = params.get('BASE_VOLUME', 0)
    metrics = calc_metrics(trades, df, bv, params)

    buys = [t for t in trades if t['direction'] == 'BUY']
    sells = [t for t in trades if t['direction'] == 'SELL']
    print(f"\n  交易统计:")
    print(f"    买入: {len(buys)}次, 合计 {sum(b['volume'] for b in buys)}股, {total_buy_amt:,.0f}元")
    print(f"    卖出: {len(sells)}次, 合计 {sum(s['volume'] for s in sells)}股, {total_sell_amt:,.0f}元")

    if metrics:
        total_pnl = metrics['total_pnl']
        slippage_cost = metrics.get('slippage_cost', 0)
        print(f"    预估盈亏: {total_pnl:+,.2f}元  (滑点成本: {slippage_cost:,.2f}元)")
        print(f"\n  绩效归因:")
        print(f"    回报率:        {metrics.get('return_pct', 0):+.2f}%")
        print(f"    胜率:          {metrics.get('win_rate', 0):.1f}% ({metrics.get('total_pairs', 0)}笔配对)")
        if metrics.get('sharpe') is not None:
            print(f"    Sharpe 比率:   {metrics['sharpe']:.2f}")
            print(f"    Sortino 比率:  {metrics['sortino']:.2f}")
            print(f"    最大回撤:      {metrics['max_drawdown']:.1f}%")
        else:
            print(f"    Sharpe / 回撤: 交易不足(需≥3笔), 待积累")

    # 分时打分轨迹摘要
    print(f"\n  {'─'*76}")
    print(f"  打分轨迹 (买入分≥{params['SWING_BUY_SIGNAL_THRESHOLD']} 或 卖出分≥{params['SWING_SELL_SIGNAL_THRESHOLD']} 的K线):")
    print(f"  {'─'*76}")
    highlighted = [e for e in bar_log
                   if e['buy_score'] >= params['SWING_BUY_SIGNAL_THRESHOLD']
                   or e['sell_score'] >= params['SWING_SELL_SIGNAL_THRESHOLD']]
    for e in highlighted:
        action_mark = f" *** {e['action']}" if e['action'] != '-' else ""
        print(f"  {e['timestamp']:<18} 买={e['buy_score']}/{e['buy_threshold']} "
              f"卖={e['sell_score']}/{e['sell_threshold']} "
              f"RSI={e['rsi']} 趋势={e['trend']}{action_mark}")


def calc_metrics(trades, df, base_volume, params):
    """计算绩效指标：回报率、Sharpe、最大回撤、胜率

    交易数 < 5 时，Sharpe/Sortino 统计意义不足，仅输出交易级指标。
    """
    if not trades:
        return {}

    closes = df['close'].values
    n = len(closes)

    # FIFO 配对盈亏
    pnl_result = total_pnl_and_pairs(trades, base_volume, closes)
    total_pnl = pnl_result['total_pnl']
    total_pairs = pnl_result['total_pairs']
    wins = pnl_result['wins']
    win_rate = wins / total_pairs * 100 if total_pairs > 0 else 0

    # 初始权益（首笔交易前的底仓市值）
    first_bar = trades[0]['bar']
    ref_bar = max(0, first_bar - 1)
    initial_equity = base_volume * closes[ref_bar] if base_volume > 0 and closes[ref_bar] > 0 else 150000.0
    if initial_equity <= 0:
        initial_equity = 150000.0

    # 回报率
    return_pct = total_pnl / initial_equity * 100

    # 只有足够交易时才计算 Sharpe/MaxDD（需要交易权益曲线）
    sharpe = 0.0
    sortino = 0.0
    max_dd = 0.0

    if len(trades) >= 3:
        # 构建策略权益曲线（相对基线的增量）
        equity = np.full(n, initial_equity)
        held = base_volume
        cash = 0.0
        trade_idx = 0
        for i in range(ref_bar + 1, n):
            while trade_idx < len(trades) and trades[trade_idx]['bar'] == i:
                t = trades[trade_idx]
                if t['direction'] == 'BUY':
                    cash -= t['amount']
                    held += t['volume']
                else:
                    cash += t['amount']
                    held -= t['volume']
                trade_idx += 1
            equity[i] = initial_equity + cash + (held - base_volume) * closes[i]

        eq_active = equity[ref_bar:]
        if len(eq_active) > 3:
            eq_safe = np.maximum(eq_active, 0.01)
            log_ret = np.diff(np.log(eq_safe))
            log_ret = log_ret[~np.isnan(log_ret) & ~np.isinf(log_ret)]
            if len(log_ret) > 2:
                mean_ret = np.mean(log_ret)
                std_ret = np.std(log_ret, ddof=1)
                bars_per_year = 250 * 48
                sharpe = (mean_ret / std_ret) * np.sqrt(bars_per_year) if std_ret > 0 else 0
                downside = log_ret[log_ret < 0]
                ds = np.std(downside, ddof=1) if len(downside) > 1 else std_ret
                sortino = (mean_ret / ds) * np.sqrt(bars_per_year) if ds > 0 else 0
            peak = np.maximum.accumulate(eq_active)
            dd = (peak - eq_active) / np.where(peak > 0, peak, 1.0)
            max_dd = float(np.max(dd)) * 100

    # 滑点成本估算
    slippage_cost = 0.0
    for t in trades:
        tag = t.get('tag', '')
        if '滑点' in tag:
            # 从 tag 中提取滑点差额
            price = t['price']; volume = t['volume']
            # 逆向计算理论价格
            bps = params.get('SLIPPAGE_BPS', 5.0) / 15000.0
            if t['direction'] == 'BUY':
                theo_price = price / (1 + bps)
            else:
                theo_price = price / (1 - bps)
            slippage_cost += abs(price - theo_price) * volume

    result = {
        'total_pnl': float(total_pnl),
        'total_trades': len(trades),
        'return_pct': round(return_pct, 2),
        'win_rate': round(win_rate, 1),
        'total_pairs': total_pairs,
        'slippage_cost': round(slippage_cost, 2),
        'sharpe': round(sharpe, 2) if len(trades) >= 3 else None,
        'sortino': round(sortino, 2) if len(trades) >= 3 else None,
        'max_drawdown': round(max_dd, 2) if len(trades) >= 3 else None,
    }
    return result


def total_pnl_and_pairs(trades, base_volume, closes):
    """FIFO 配对计算盈亏和胜率（确保每笔卖出只匹配其前面的买入）"""
    buys = [t for t in trades if t['direction'] == 'BUY']
    sells = [t for t in trades if t['direction'] == 'SELL']
    total_pnl = 0.0
    wins = 0
    pairs = 0
    buy_q = []
    for t in trades:
        if t['direction'] == 'BUY':
            buy_q.append(dict(t))  # copy
        elif t['direction'] == 'SELL' and buy_q:
            remaining = t['volume']
            while remaining > 0 and buy_q:
                b = buy_q[0]
                matched = min(remaining, b['volume'])
                pair_pnl = matched * (t['price'] - b['price'])
                total_pnl += pair_pnl
                if pair_pnl > 0:
                    wins += 1
                pairs += 1
                remaining -= matched
                b['volume'] -= matched
                if b['volume'] <= 0:
                    buy_q.pop(0)
    return {'total_pnl': total_pnl, 'wins': wins, 'total_pairs': pairs}


def main():
    parser = argparse.ArgumentParser(description='摆动交易离线回放调参')
    parser.add_argument('csv_path', help='录制的5分钟K线CSV文件路径')
    parser.add_argument('--1m-csv', help='对应的1分钟K线CSV文件路径（可选）')
    parser.add_argument('--params', '-p', help='JSON参数文件路径')
    parser.add_argument('--base-volume', type=int, help='底仓股数')
    parser.add_argument('--buy-threshold', type=int, help='买入信号分数阈值')
    parser.add_argument('--sell-threshold', type=int, help='卖出信号分数阈值')
    parser.add_argument('--buy-cooldown', type=int, help='买入冷却时间(秒)')
    parser.add_argument('--sell-cooldown', type=int, help='卖出冷却时间(秒)')
    parser.add_argument('--max-buys', type=int, help='每日最大买入次数')
    parser.add_argument('--max-sells', type=int, help='每日最大卖出次数')
    parser.add_argument('--buy-ratio', type=float, help='单次买入占底仓比例')
    parser.add_argument('--sell-ratio', type=float, help='单次卖出占底仓比例')
    parser.add_argument('--min-profit', type=float, help='最小盈利要求')
    parser.add_argument('--rsi-oversold', type=int, help='RSI超卖阈值')
    parser.add_argument('--rsi-overbought', type=int, help='RSI超买阈值')
    parser.add_argument('--quiet', '-q', action='store_true', help='仅输出交易列表')
    parser.add_argument('--json', '-j', action='store_true', help='输出JSON格式摘要')

    args = parser.parse_args()
    params = dict(DEFAULT_PARAMS)

    # 从JSON文件加载参数
    if args.params:
        with open(args.params, 'r') as f:
            overrides = json.load(f)
        params.update(overrides)

    # 命令行覆盖
    cli_map = {
        'base_volume': 'BASE_VOLUME',
        'buy_threshold': 'SWING_BUY_SIGNAL_THRESHOLD',
        'sell_threshold': 'SWING_SELL_SIGNAL_THRESHOLD',
        'buy_cooldown': 'SWING_BUY_COOLDOWN',
        'sell_cooldown': 'SWING_SELL_COOLDOWN',
        'max_buys': 'SWING_MAX_DAILY_BUYS',
        'max_sells': 'SWING_MAX_DAILY_SELLS',
        'buy_amount': 'SWING_BUY_AMOUNT',
        'sell_amount': 'SWING_SELL_AMOUNT',
        'min_profit': 'SWING_MIN_PROFIT_RATIO',
        'rsi_oversold': 'SWING_RSI_OVERSOLD',
        'rsi_overbought': 'SWING_RSI_OVERBOUGHT',
    }
    for arg_name, param_key in cli_map.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            params[param_key] = val

    if not os.path.exists(args.csv_path):
        print(f"错误: 文件不存在: {args.csv_path}")
        sys.exit(1)

    # 自动检测1分钟CSV（命名规则: {stock}_{date}.csv → {stock}_1m_{date}.csv）
    path_1m = getattr(args, '1m_csv', None)
    if not path_1m and params.get('ENABLE_1M_CONFIRMATION', True):
        base = args.csv_path
        # data/swing_replay/300394.SZ_20260723.csv → 300394.SZ_1m_20260723.csv
        import re
        auto_1m = re.sub(r'(_\d{8})\.csv$', r'_1m\1.csv', os.path.basename(base))
        auto_path = os.path.join(os.path.dirname(base), auto_1m)
        if os.path.exists(auto_path):
            path_1m = auto_path
            print(f"自动检测到1分钟数据: {auto_1m}")

    bar_log, trades, df = replay(args.csv_path, params, verbose=not args.quiet,
                                 path_1m=path_1m)

    if getattr(args, 'json', False):
        # 机器可读 JSON 输出
        bv = params.get('BASE_VOLUME', 0)
        metrics = calc_metrics(trades, df, bv, params) if trades else {}
        buys = [t for t in trades if t['direction'] == 'BUY']
        sells = [t for t in trades if t['direction'] == 'SELL']
        result = {
            'stock': os.path.basename(args.csv_path).split('_')[0],
            'trades': len(trades),
            'buys': len(buys), 'sells': len(sells),
            'buy_volume': sum(b['volume'] for b in buys),
            'sell_volume': sum(s['volume'] for s in sells),
            'pnl': metrics.get('total_pnl', 0),
            'return_pct': metrics.get('return_pct', 0),
            'win_rate': metrics.get('win_rate', 0),
            'sharpe': metrics.get('sharpe'),
            'max_drawdown': metrics.get('max_drawdown'),
            'slippage_cost': metrics.get('slippage_cost', 0),
        }
        import json as _json
        print('__JSON_RESULT__' + _json.dumps(result, ensure_ascii=False))
    else:
        print_report(bar_log, trades, df, params)


if __name__ == '__main__':
    main()
