#!/usr/bin/env python3
"""用今天录制的数据回测当前逻辑"""
import sys, os, json, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from MyTT import MA, MACD, RSI, KDJ, BOLL, ATR

# ===== 当前参数 =====
PARAMS = {
    'BUY_TH': 2, 'SELL_TH': 3,
    'BOLL_PERIOD': 20, 'BOLL_STD': 2.0,
    'RSI_PERIOD': 14, 'RSI_OVERSOLD': 30, 'RSI_OVERBOUGHT': 70,
    'MACD_FAST': 6, 'MACD_SLOW': 13, 'MACD_SIGNAL': 5,
    'KDJ_PERIOD': 9, 'KDJ_K_OVERSOLD': 20, 'KDJ_K_OVERBOUGHT': 80,
    'VOL_MA_PERIOD': 20, 'VOL_SPIKE': 1.5,
    'TREND_PERIOD': 20, 'TREND_SLOPE_TH': 0.0008,
    'TREND_BUY_BOOST': 0, 'TREND_SELL_SUPPRESS': 1,
    'TREND_SELL_BOOST': 1, 'TREND_BUY_SUPPRESS': 2,
    'BUY_COOLDOWN': 180, 'SELL_COOLDOWN': 300,
    'MAX_BUYS': 99, 'MAX_SELLS': 99,
    'BUY_RATIO': 0.25, 'SELL_RATIO': 0.25,
    'MIN_BUY_VOL': 200, 'MIN_SELL_VOL': 200,
    'MIN_PROFIT': 0.005,
    'ATR_MULT': 1.0,
    'VOLUME_RATIO_LIMIT': 1.0,
    # P0/P1/P2 新特性
    'TRAILING_ENABLED': True, 'TRAILING_ACTIVATION': 0.03,
    'TRAILING_BREAKEVEN': 0.02, 'TRAILING_DISTANCE': 0.02,
    'ATR_ADAPTIVE': True, 'ATR_REF': 0.025, 'ATR_MIN': 0.5, 'ATR_MAX': 1.5,
    'USE_VWAP': True, 'VWAP_BOOST': 1, 'VWAP_PENALTY': 1,
    'COOLDOWN_DYNAMIC': True, 'COOLDOWN_TREND': 0.5, 'COOLDOWN_RANGE': 1.5,
    'USE_ADX': True, 'ADX_MIN': 18, 'ADX_STRONG': 40,
    'HIDDEN_DIV': True, 'HIDDEN_BOOST': 2,
    'TRIPLE_DIV': True,
    'SLIPPAGE_BPS': 5.0,
}

def load_csv(path):
    import pandas as pd
    df = pd.read_csv(path)
    for c in ['open','high','low','close']:
        df[c] = df[c].astype(float)
    df['volume'] = df['volume'].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    # Filter to today only
    df = df[df['timestamp'].dt.date == pd.Timestamp('2026-07-28').date()]
    return df

def market_structure(close):
    """当日市场结构（最近48根5mK线，lookback=5）"""
    n_total = len(close); n_window = min(48, n_total)
    recent = close[-n_window:]; n = len(recent); offset = n_total - n; lookback = 5
    if n < lookback * 3: return {'trend': 'range', 'new_swing': None}
    highs, lows = [], []
    for i in range(lookback, n - lookback):
        left = recent[i-lookback:i]; right = recent[i+1:i+lookback+1]
        if all(recent[i] >= x for x in left) and all(recent[i] >= x for x in right):
            highs.append({'price': float(recent[i]), 'idx': i + offset})
        if all(recent[i] <= x for x in left) and all(recent[i] <= x for x in right):
            lows.append({'price': float(recent[i]), 'idx': i + offset})
    if len(highs) < 2 or len(lows) < 2: return {'trend': 'range', 'new_swing': None}
    h1, h2 = highs[-2], highs[-1]; l1, l2 = lows[-2], lows[-1]
    ci = n_total - 1; ns = None
    if h2['price'] > h1['price'] and l2['price'] > l1['price']:
        trend = 'up'
        if l2['idx'] >= ci - 2: ns = 'HL'
    elif h2['price'] < h1['price'] and l2['price'] < l1['price']:
        trend = 'down'
        if h2['idx'] >= ci - 2: ns = 'LH'
    else:
        trend = 'range'
    return {'trend': trend, 'new_swing': ns,
            'last_high': h2['price'], 'last_low': l2['price'],
            'prev_high': h1['price'], 'prev_low': l1['price']}

def calc_indicators(close, open_, high, low, volume):
    n = len(close)
    min_len = max(PARAMS['BOLL_PERIOD'], PARAMS['RSI_PERIOD'],
                  PARAMS['MACD_SLOW'] + PARAMS['MACD_SIGNAL'],
                  PARAMS['KDJ_PERIOD'] + 3)
    if n < min_len:
        return None
    upper, mid, lower = BOLL(close, N=PARAMS['BOLL_PERIOD'], P=PARAMS['BOLL_STD'])
    rsi_series = RSI(close, N=PARAMS['RSI_PERIOD'])
    dif, dea, hist = MACD(close, SHORT=PARAMS['MACD_FAST'], LONG=PARAMS['MACD_SLOW'], M=PARAMS['MACD_SIGNAL'])
    vol_ma = MA(volume, N=PARAMS['VOL_MA_PERIOD'])
    k, d, j = KDJ(close, high, low, N=PARAMS['KDJ_PERIOD'], M1=3, M2=3)
    # trend slope
    trend_slope = 0.0
    tn = PARAMS['TREND_PERIOD']
    if n >= tn:
        recent = close[-tn:]
        x = np.arange(tn)
        s = (tn * np.sum(x * recent) - np.sum(x) * np.sum(recent)) / (tn * np.sum(x**2) - np.sum(x)**2)
        avg = np.mean(recent)
        if avg > 0: trend_slope = float(s / avg)
    # P2: ADX / P1: VWAP
    adx_v, vwap_v = 20.0, float(close[-1])
    # VWAP
    tp = (high + low + close) / 3.0
    cpv = np.cumsum(tp * volume); cv = np.cumsum(volume)
    if cv[-1] > 0: vwap_v = float(cpv[-1] / cv[-1])

    return {
        'close': float(close[-1]), 'open': float(open_[-1]),
        'high': float(high[-1]), 'low': float(low[-1]),
        'prev_close': float(close[-2]) if n >= 2 else float(close[-1]),
        'boll_upper': float(upper[-1]), 'boll_mid': float(mid[-1]), 'boll_lower': float(lower[-1]),
        'rsi': float(rsi_series[-1]),
        'macd': float(dif[-1]), 'macd_signal': float(dea[-1]), 'macd_hist': float(hist[-1]),
        'volume': float(volume[-1]), 'volume_ma': float(vol_ma[-1]),
        'kdj_k': float(k[-1]), 'kdj_d': float(d[-1]), 'kdj_j': float(j[-1]),
        'prev_macd_hist': float(hist[-2]) if n >= 2 else 0.0,
        'prev_rsi': float(rsi_series[-2]) if n >= 2 else 50.0,
        'prev_kdj_k': float(k[-2]) if len(k) >= 2 else 50.0,
        'prev_kdj_d': float(d[-2]) if len(d) >= 2 else 50.0,
        'trend_slope': trend_slope,
        'atr': float(ATR(close, high, low, N=14)[-1]) / float(close[-1]),
        'close_1m': float(close[-1]),
        'rsi_1m': float(rsi_series[-1]),
        'macd_hist_1m': float(hist[-1]),
        'prev_macd_hist_1m': float(hist[-2]) if n >= 2 else 0.0,
        'adx': adx_v, 'vwap': vwap_v,
        'structure': market_structure(close),
    }

def score_buy(ind):
    score, det = 0, []
    p, r, b = ind['close'], ind['rsi'], ind['boll_lower']
    mh, pm = ind['macd_hist'], ind['prev_macd_hist']
    v, vm = ind['volume'], ind['volume_ma']
    if b > 0 and p <= b * 1.005: score += 2; det.append(f"触及下轨({p:.2f}<={b:.2f})")
    if ind.get('div_bullish', False): score += 2; det.append("RSI底背离")
    if r < PARAMS['RSI_OVERSOLD']: score += 2; det.append(f"RSI超卖({r:.1f})")
    if r < PARAMS['RSI_OVERSOLD'] - 5: score += 1; det.append(f"RSI深度超卖({r:.1f})")
    if mh > 0 and pm < 0: score += 2; det.append("MACD金叉")
    if mh > 0: score += 1; det.append("MACD柱>0")
    if vm > 0 and v > vm * PARAMS['VOL_SPIKE']: score += 1; det.append("放量确认")
    k, d, pk, pd = ind['kdj_k'], ind['kdj_d'], ind['prev_kdj_k'], ind['prev_kdj_d']
    j = ind['kdj_j']
    if pk <= pd and k > d:
        if k < PARAMS['KDJ_K_OVERSOLD']: score += 2; det.append(f"KDJ低位金叉(K={k:.1f})")
        else: score += 1; det.append(f"KDJ金叉(K={k:.1f})")
    if j < 0: score += 1; det.append(f"KDJ-J超卖(J={j:.1f})")
    if k < PARAMS['KDJ_K_OVERSOLD'] and d < PARAMS['KDJ_K_OVERSOLD']: score += 1; det.append(f"KDJ超卖区")
    # P1: VWAP
    if PARAMS.get('USE_VWAP', True):
        vwap = ind.get('vwap', 0); pr = ind.get('close_1m', ind['close'])
        if vwap > 0:
            if pr < vwap: score += PARAMS.get('VWAP_BOOST', 1); det.append("VWAP下方")
            else: score -= PARAMS.get('VWAP_PENALTY', 1); det.append("VWAP上方")
    # 1m confirmation
    return score, det

def score_sell(ind):
    score, det = 0, []
    p, r, b = ind['close'], ind['rsi'], ind['boll_upper']
    high_p = ind.get('high', p)  # 盘中最高价
    mh, pm = ind['macd_hist'], ind['prev_macd_hist']
    v, vm = ind['volume'], ind['volume_ma']
    # 用最高价判断上轨触及
    if b > 0 and high_p >= b * 0.995: score += 2; det.append(f"触及上轨(H{high_p:.2f}>={b:.2f})")
    if ind.get('div_bearish', False): score += 2; det.append("MACD顶背离")
    if r > PARAMS['RSI_OVERBOUGHT']: score += 2; det.append(f"RSI超买({r:.1f})")
    if r > PARAMS['RSI_OVERBOUGHT'] + 5: score += 1; det.append(f"RSI深度超买({r:.1f})")
    if mh < 0 and pm > 0: score += 2; det.append("MACD死叉")
    if mh < 0: score += 1; det.append("MACD柱<0")
    if vm > 0 and v > vm * PARAMS['VOL_SPIKE']: score += 1; det.append("放量")
    k, d, pk, pd = ind['kdj_k'], ind['kdj_d'], ind['prev_kdj_k'], ind['prev_kdj_d']
    j = ind['kdj_j']
    if pk >= pd and k < d:
        if k > PARAMS['KDJ_K_OVERBOUGHT']: score += 2; det.append(f"KDJ高位死叉(K={k:.1f})")
        else: score += 1; det.append(f"KDJ死叉(K={k:.1f})")
    if j > 100: score += 1; det.append(f"KDJ-J超买(J={j:.1f})")
    if k > PARAMS['KDJ_K_OVERBOUGHT'] and d > PARAMS['KDJ_K_OVERBOUGHT']: score += 1; det.append(f"KDJ超买区")
    # P1: VWAP
    if PARAMS.get('USE_VWAP', True):
        vwap = ind.get('vwap', 0); pr = ind.get('close_1m', ind['close'])
        if vwap > 0:
            if pr > vwap: score += PARAMS.get('VWAP_BOOST', 1); det.append("VWAP上方")
            else: score -= PARAMS.get('VWAP_PENALTY', 1); det.append("VWAP下方")
    return score, det

def get_trend(slope):
    if slope > PARAMS['TREND_SLOPE_TH']: return 'up'
    elif slope < -PARAMS['TREND_SLOPE_TH']: return 'down'
    return 'range'

def thresholds(trend):
    if trend == 'up':
        return (PARAMS['BUY_TH'] - PARAMS['TREND_BUY_BOOST'],
                PARAMS['SELL_TH'] + PARAMS['TREND_SELL_SUPPRESS'])
    elif trend == 'down':
        return (PARAMS['BUY_TH'] + PARAMS['TREND_BUY_SUPPRESS'],
                PARAMS['SELL_TH'] - PARAMS['TREND_SELL_BOOST'])
    return (PARAMS['BUY_TH'], PARAMS['SELL_TH'])

def backtest_stock(stock_code, base_volume):
    """回测单只股票，返回交易列表"""
    replay_dir = os.path.join('data', 'swing_replay')
    f5m = os.path.join(replay_dir, f'{stock_code}_20260728.csv')
    f1m = os.path.join(replay_dir, f'{stock_code}_1m_20260728.csv')
    if not os.path.exists(f5m):
        return [], f"无5m数据"

    # Load ALL data for indicator window, but only trade on today
    import pandas as pd
    df_all = pd.read_csv(f5m)
    for c in ['open','high','low','close']:
        df_all[c] = df_all[c].astype(float)
    df_all['volume'] = df_all['volume'].astype(float)
    df_all['timestamp'] = pd.to_datetime(df_all['timestamp'])
    today_mask = df_all['timestamp'].dt.date == pd.Timestamp('2026-07-28').date()
    df_all = df_all.reset_index(drop=True)
    today_indices = [i for i, m in enumerate(today_mask) if m]

    if len(today_indices) < 10:
        return [], f"today bars too few ({len(today_indices)})"

    # Load 1m data for confirmation
    close_1m_all = None
    if os.path.exists(f1m):
        df1 = pd.read_csv(f1m)
        df1['timestamp'] = pd.to_datetime(df1['timestamp'])
        df1 = df1[df1['timestamp'].dt.date == pd.Timestamp('2026-07-28').date()]
        close_1m_all = df1['close'].values

    # State
    swing_entry_price = 0.0
    buy_count = 0; sell_count = 0
    buy_volume_total = 0; sell_volume_total = 0
    last_buy_time = 0; last_sell_time = 0
    last_buy_price = 0.0
    last_trend = ''; down_trend_buys = 0
    recent_lows = []
    trades = []

    min_indicator_bars = max(PARAMS['BOLL_PERIOD'], PARAMS['RSI_PERIOD'],
                             PARAMS['MACD_SLOW'] + PARAMS['MACD_SIGNAL'],
                             PARAMS['KDJ_PERIOD'] + 3)
    first_today = today_indices[0] if today_indices else 0

    # Use historical bars for indicator warmup, trade from first today bar
    if first_today < min_indicator_bars:
        return [], f"need {min_indicator_bars} bars, only {first_today} before today"

    for idx, i in enumerate(today_indices):
        # Indicators already have enough history (bars before today)
        # Build indicators using all data up to i
        row = df_all.iloc[i]
        time_str = str(row['timestamp'])
        # Build indicator window using all bars up to i
        close = df_all['close'].values[:i+1]
        open_ = df_all['open'].values[:i+1]
        high = df_all['high'].values[:i+1]
        low = df_all['low'].values[:i+1]
        volume = df_all['volume'].values[:i+1]

        ind = calc_indicators(close, open_, high, low, volume)
        if ind is None: continue

        # === 5m 只看趋势方向 ===
        trend = get_trend(ind['trend_slope'])
        # 结构趋势优先
        st = ind.get('structure', {})
        if st and st.get('trend', 'range') != 'range':
            trend = st['trend']

        # === 1m 打分找买卖点 ===
        buy_1m = sell_1m = 0
        if close_1m_all is not None:
            c1m = close_1m_all[:min(idx*5+5, len(close_1m_all))]
            if len(c1m) >= 30:
                r1 = RSI(c1m, N=min(14, len(c1m)-2))
                rsi1 = float(r1[-1]) if len(r1) > 0 else 50.0
                prev_rsi1 = float(r1[-2]) if len(r1) >= 2 else 50.0
                _, _, h1 = MACD(c1m, SHORT=6, LONG=13, M=5)
                mh1 = float(h1[-1]) if len(h1) > 0 else 0.0
                pm1 = float(h1[-2]) if len(h1) >= 2 else 0.0
                # 真实 1m 布林和 KDJ
                up1, md1, lo1 = BOLL(c1m, N=20, P=2.0)
                k1, d1, j1 = KDJ(c1m, c1m, c1m, N=9, M1=3, M2=3)
                ind1m = dict(close=float(c1m[-1]), rsi=rsi1, prev_rsi=prev_rsi1,
                    macd_hist=mh1, prev_macd_hist=pm1,
                    boll_lower=float(lo1[-1]), boll_upper=float(up1[-1]),
                    volume=10000, volume_ma=10000,
                    kdj_k=float(k1[-1]), kdj_d=float(d1[-1]), kdj_j=float(j1[-1]),
                    prev_kdj_k=float(k1[-2]) if len(k1)>=2 else 50,
                    prev_kdj_d=float(d1[-2]) if len(d1)>=2 else 50,
                    high=float(c1m[-1]), low=float(c1m[-1]), open=float(c1m[-1]),
                    structure={'trend':'range','new_swing':None})
                buy_1m, buy_1m_det = score_buy(ind1m)
                sell_1m, sell_1m_det = score_sell(ind1m)
            else:
                buy_1m = sell_1m = 0
        else:
            buy_1m = sell_1m = 0

        # 5m 打分（始终计算，用于双确认）
        buy_5m, buy_5m_det = score_buy(ind)
        sell_5m, sell_5m_det = score_sell(ind)

        # 1m 主打分（用于触发时机），5m 做确认
        if buy_1m > 0 or sell_1m > 0:
            buy_score, buy_det = buy_1m, buy_1m_det
            sell_score, sell_det = sell_1m, sell_1m_det
        else:
            buy_score, buy_det = buy_5m, buy_5m_det
            sell_score, sell_det = sell_5m, sell_5m_det
            buy_1m = buy_5m; sell_1m = sell_5m  # fallback

        # 5m 结构信号叠加
        ns = st.get('new_swing') if st else None
        if ns == 'HL': buy_score += 3; buy_det.append("5mHL")
        if ns == 'LH': sell_score += 3; sell_det.append("5mLH")

        buy_th, sell_th = thresholds(trend)

        buy_triggered = buy_score >= buy_th and buy_5m >= buy_th
        sell_triggered = sell_score >= sell_th and sell_5m >= sell_th

        # 趋势方向过滤
        if trend == 'up':
            buy_triggered = False
            last_trend = 'up'
        elif trend == 'down':
            if last_trend != 'down':
                down_trend_buys = 0; last_trend = 'down'
            if sell_count == 0:
                buy_triggered = False  # 下跌先卖后买
        else:
            last_trend = 'range'

        # Determine which signal
        direction = None
        if buy_triggered and sell_triggered:
            direction = 'sell'  # priority
        elif buy_triggered:
            direction = 'buy'
        elif sell_triggered:
            direction = 'sell'

        if direction is None: continue

        # P2: ADX filter
        if PARAMS.get('USE_ADX', True) and ind.get('adx', 20) < PARAMS.get('ADX_MIN', 18):
            continue

        bar_time = row['timestamp'].timestamp()
        current_price = ind['close']

        # P1: Dynamic cooldown
        def _dyn_cd(base_cd, trend, adx_val):
            if not PARAMS.get('COOLDOWN_DYNAMIC', True): return base_cd
            if adx_val > PARAMS.get('ADX_STRONG', 40): mult = 0.3
            elif trend in ('up','down'): mult = PARAMS.get('COOLDOWN_TREND', 0.5)
            else: mult = PARAMS.get('COOLDOWN_RANGE', 1.5)
            return max(30, int(base_cd * mult))

        # P0: Trailing stop before buy
        if direction == 'sell' and swing_entry_price > 0 and PARAMS.get('TRAILING_ENABLED', True):
            profit = (current_price - swing_entry_price) / swing_entry_price
            activation = PARAMS.get('TRAILING_ACTIVATION', 0.03)
            breakeven = PARAMS.get('TRAILING_BREAKEVEN', 0.02)
            distance = PARAMS.get('TRAILING_DISTANCE', 0.02)
            # Track peak
            peak_key = f'_peak_{stock_code}'
            peak = max(getattr(backtest_stock, peak_key, swing_entry_price), current_price)
            setattr(backtest_stock, peak_key, peak)
            trail_triggered = False; tag = ''
            if profit >= breakeven and current_price <= swing_entry_price:
                trail_triggered = True; tag = '保本止盈'
            elif profit >= activation:
                stop_p = peak * (1 - distance)
                if current_price <= stop_p:
                    trail_triggered = True; tag = f'追踪止盈(peak={peak:.2f})'
            if trail_triggered:
                sell_vol = max(int(base_volume * PARAMS['SELL_RATIO']), PARAMS['MIN_SELL_VOL'])
                sell_vol = int(round(sell_vol / 100)) * 100
                if sell_vol >= PARAMS['MIN_SELL_VOL']:
                    slip = current_price * PARAMS.get('SLIPPAGE_BPS', 5.0) / 10000.0
                    ep = current_price - max(slip, 0.01)
                    trades.append((time_str, 'TRAIL', sell_vol, ep, ep*sell_vol, 0, tag))
                    sell_count += 1; sell_volume_total += sell_vol
                    last_sell_time = bar_time; swing_entry_price = 0.0; base_volume -= sell_vol
                    setattr(backtest_stock, peak_key, 0)
                    continue

        if direction == 'buy':
            if buy_count >= PARAMS['MAX_BUYS']: continue
            if trend == 'down' and len(recent_lows) >= 2:
                if recent_lows[-1] <= recent_lows[-2]: continue
            atr_ratio = ind.get('atr', 0.003)
            if atr_ratio <= 0: atr_ratio = 0.003
            step = max(atr_ratio * 1.0, 0.003)
            elapsed = bar_time - last_buy_time
            price_dropped = last_buy_price > 0 and current_price <= last_buy_price * (1 - step)
            cooldown_ok = elapsed >= _dyn_cd(PARAMS['BUY_COOLDOWN'], trend, ind.get('adx', 20))
            if last_buy_time > 0 and (not price_dropped or not cooldown_ok):
                continue
            buy_vol = max(int(base_volume * PARAMS['BUY_RATIO']), PARAMS['MIN_BUY_VOL'])
            buy_vol = int(round(buy_vol / 100)) * 100
            # P1: ATR adaptive
            if PARAMS.get('ATR_ADAPTIVE', True) and ind.get('atr', 0) > 0:
                ratio = PARAMS.get('ATR_REF', 0.025) / ind['atr']
                ratio = max(PARAMS.get('ATR_MIN', 0.5), min(PARAMS.get('ATR_MAX', 1.5), ratio))
                buy_vol = max(PARAMS['MIN_BUY_VOL'], int(round(buy_vol * ratio / 100)) * 100)
            if buy_vol < PARAMS['MIN_BUY_VOL']: continue
            if buy_vol * current_price < 10000: continue
            slip = current_price * PARAMS.get('SLIPPAGE_BPS', 5.0) / 10000.0
            ep = current_price + max(slip, 0.01)
            amount = buy_vol * ep
            trades.append((time_str, 'BUY', buy_vol, ep, amount, buy_score))
            if swing_entry_price > 0:
                old_total = swing_entry_price * buy_volume_total
                swing_entry_price = (old_total + amount) / (buy_volume_total + buy_vol) if buy_volume_total + buy_vol > 0 else ep
            else:
                swing_entry_price = ep
            buy_count += 1; buy_volume_total += buy_vol
            last_buy_time = bar_time; last_buy_price = ep
            if trend == 'down': down_trend_buys += 1
            base_volume += buy_vol

        elif direction == 'sell':
            if sell_count >= PARAMS['MAX_SELLS']: continue
            if bar_time - last_sell_time < _dyn_cd(PARAMS['SELL_COOLDOWN'], trend, ind.get('adx', 20)): continue
            if swing_entry_price > 0:
                min_sell = swing_entry_price * (1 + PARAMS['MIN_PROFIT'])
                if current_price < min_sell: continue
            sellable = base_volume
            sell_vol = max(int(sellable * PARAMS['SELL_RATIO']), PARAMS['MIN_SELL_VOL'])
            sell_vol = int(round(sell_vol / 100)) * 100
            sell_vol = min(sell_vol, base_volume)
            if sell_vol < PARAMS['MIN_SELL_VOL']:
                if base_volume >= 100: sell_vol = base_volume
                else: continue
            slip = current_price * PARAMS.get('SLIPPAGE_BPS', 5.0) / 10000.0
            ep = current_price - max(slip, 0.01)
            amount = sell_vol * ep
            profit = (ep - swing_entry_price) / swing_entry_price * 100 if swing_entry_price > 0 else 0
            trades.append((time_str, 'SELL', sell_vol, ep, amount, sell_score, f'{profit:+.2f}%'))
            sell_count += 1; sell_volume_total += sell_vol
            last_sell_time = bar_time; base_volume -= sell_vol

    return trades, None


# ===== 主程序 =====
stocks = [
    ('300017.SZ', 8800), ('300204.SZ', 4600),
    ('300557.SZ', 100), ('603938.SH', 100), ('300826.SZ', 1400),
]

print("=" * 70)
print("当前逻辑回测 - 2026-07-28 数据")
print(f"买入阈值={PARAMS['BUY_TH']} 卖出阈值={PARAMS['SELL_TH']} 单笔={PARAMS['BUY_RATIO']*100:.0f}%")
print(f"冷却={PARAMS['BUY_COOLDOWN']}s 阶梯=ATR动态 最小盈利={PARAMS['MIN_PROFIT']*100:.1f}%")
print("=" * 70)

all_trades = []
for stock_code, base_vol in stocks:
    trades, err = backtest_stock(stock_code, base_vol)
    if err:
        print(f"{stock_code}: {err}")
        continue
    if not trades:
        print(f"{stock_code}: 无交易")
        continue
    print(f"\n{stock_code} (底仓{base_vol}股):")
    for t in trades:
        time_str, direction, vol, price, amount = t[:5]
        score = t[5]
        tag = t[6] if len(t) > 6 else ''
        tag_str = f' {tag}' if tag else ''
        print(f"  {time_str[11:19] if ' ' in time_str else time_str[-8:]} {direction} {vol}gu @{price:.2f} Y{amount:,.0f} (s{score}){tag_str}")
    all_trades.extend(trades)

print(f"\n总计: {len(all_trades)} 笔交易")
