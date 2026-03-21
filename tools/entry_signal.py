from __future__ import annotations

"""
entry_signal.py - 入场信号聚合与风控计算

核心思想:
  1. 聚合所有 tools 模块的底层信号，通过加权评分得出综合方向判断
  2. 提供三种止损方法 (ATR / 结构 / VWAP)，以及多级止盈目标
  3. CHOP 指数作为市场状态修正因子，影响信号可靠性权重

评分体系 (满分 ±100):
  趋势结构   35分: SuperTrend(20) + SAR(10) + Ichimoku(5)
  资金动量   30分: MACD(12) + CMF(10) + VWAP位置(8)
  情绪极值   20分: RSI背离(12) + RSI极值(5) + Williams%R(3)
  宏观背景   15分: MA200(10) + MA50(5)
  市场状态修正: CHOP趋势市 × 1.2 / CHOP震荡市 × 0.7
"""

import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools.calculate import (
    load_bars, get_recent_24h, resample_daily,
    cross_detect, divergence_detect, format_report, pct_diff
)


# ==========================================
# 内部指标计算 (轻量复用，避免重复加载数据)
# ==========================================

def _vwap(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    return (tp * df['volume']).cumsum() / df['volume'].cumsum()


def _atr(df, period=14):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _macd(df, fast=12, slow=26, signal=9):
    line = df['close'].ewm(span=fast, adjust=False).mean() - \
           df['close'].ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def _cmf(df, period=20):
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / \
          (df['high'] - df['low']).replace(0, 0.001)
    return (mfm * df['volume']).rolling(period).sum() / \
           df['volume'].rolling(period).sum()


def _rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    ag = gain.rolling(window=period, min_periods=period).mean()
    al = loss.rolling(window=period, min_periods=period).mean()
    for i in range(period, len(ag)):
        ag.iloc[i] = (ag.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        al.iloc[i] = (al.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period
    return 100 - (100 / (1 + ag / al.replace(0, 0.001)))


def _williams_r(df, period=14):
    hi = df['high'].rolling(period).max()
    lo = df['low'].rolling(period).min()
    return -100 * (hi - df['close']) / (hi - lo).replace(0, 0.001)


def _supertrend(df, period=10, mult=3.0):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    hl2 = (df['high'] + df['low']) / 2
    bu = (hl2 + mult * atr).copy()
    bl = (hl2 - mult * atr).copy()
    trend = pd.Series(np.ones(len(df)), index=df.index)
    for i in range(1, len(df)):
        bu.iloc[i] = (hl2 + mult * atr).iloc[i] \
            if (hl2 + mult * atr).iloc[i] < bu.iloc[i - 1] \
               or df['close'].iloc[i - 1] > bu.iloc[i - 1] \
            else bu.iloc[i - 1]
        bl.iloc[i] = (hl2 - mult * atr).iloc[i] \
            if (hl2 - mult * atr).iloc[i] > bl.iloc[i - 1] \
               or df['close'].iloc[i - 1] < bl.iloc[i - 1] \
            else bl.iloc[i - 1]
        if trend.iloc[i - 1] == 1:
            trend.iloc[i] = -1 if df['close'].iloc[i] < bl.iloc[i] else 1
        else:
            trend.iloc[i] = 1 if df['close'].iloc[i] > bu.iloc[i] else -1
    st = pd.Series(np.where(trend == 1, bl, bu), index=df.index)
    return st, trend, bu, bl


def _parabolic_sar(df, af_start=0.02, af_step=0.02, af_max=0.2):
    hi, lo = df['high'].values, df['low'].values
    n = len(df)
    sar = np.zeros(n)
    trend = np.ones(n)
    af, ep = af_start, hi[0]
    sar[0] = lo[0]
    for i in range(1, n):
        if trend[i - 1] == 1:
            sar[i] = min(sar[i - 1] + af * (ep - sar[i - 1]),
                         lo[i - 1], lo[max(0, i - 2)])
            if lo[i] < sar[i]:
                trend[i], sar[i], ep, af = -1, ep, lo[i], af_start
            else:
                trend[i] = 1
                if hi[i] > ep:
                    ep, af = hi[i], min(af + af_step, af_max)
        else:
            sar[i] = max(sar[i - 1] + af * (ep - sar[i - 1]),
                         hi[i - 1], hi[max(0, i - 2)])
            if hi[i] > sar[i]:
                trend[i], sar[i], ep, af = 1, ep, hi[i], af_start
            else:
                trend[i] = -1
                if lo[i] < ep:
                    ep, af = lo[i], min(af + af_step, af_max)
    return pd.Series(sar, index=df.index), pd.Series(trend, index=df.index)


def _ichimoku(df):
    tenkan = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    kijun = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    return tenkan, kijun


def _chop(df, period=14):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    hl = (df['high'].rolling(period).max() -
          df['low'].rolling(period).min()).replace(0, 0.001)
    return 100 * np.log10(tr.rolling(period).sum() / hl) / np.log10(period)


# ==========================================
# 核心: 信号评分
# ==========================================

def _score_signals(df_24h, df_daily):
    """
    计算各维度信号分数，返回 (raw_score, signals_detail)。
    raw_score: float, 未经市场状态修正
    signals_detail: dict, 各信号的分数和描述
    """
    close = df_24h['close'].iloc[-1]
    signals = {}

    # ── 趋势结构 (35分) ──────────────────────────────────
    # SuperTrend (20分)
    st, st_trend, st_upper, st_lower = _supertrend(df_24h)
    st_val = int(st_trend.iloc[-1])
    st_score = 20 * st_val  # +20 多头 / -20 空头
    st_level = st_lower.iloc[-1] if st_val == 1 else st_upper.iloc[-1]
    signals['SuperTrend'] = (st_score, '多头 (+20)' if st_val == 1 else '空头 (-20)')

    # Parabolic SAR (10分)
    sar_val, sar_trend = _parabolic_sar(df_24h)
    sar_dir = int(sar_trend.iloc[-1])
    sar_score = 10 * sar_dir
    signals['SAR'] = (sar_score, '上升 (+10)' if sar_dir == 1 else '下降 (-10)')

    # Ichimoku (5分)
    tenkan, kijun = _ichimoku(df_24h)
    if not kijun.dropna().empty:
        ichi_score = 5 if close > kijun.dropna().iloc[-1] else -5
        signals['Ichimoku'] = (ichi_score,
                               f'价格{"上穿" if ichi_score > 0 else "下穿"}基准线 ({ichi_score:+d})')
    else:
        ichi_score = 0
        signals['Ichimoku'] = (0, '数据不足')

    # ── 资金动量 (30分) ──────────────────────────────────
    # MACD (12分)
    macd_line, macd_sig, macd_hist = _macd(df_24h)
    macd_cross = cross_detect(macd_line.dropna(), macd_sig.dropna())
    macd_above_zero = macd_line.iloc[-1] > 0
    if '金叉' in macd_cross:
        macd_score = 12
        macd_desc = '金叉 (+12)'
    elif '死叉' in macd_cross:
        macd_score = -12
        macd_desc = '死叉 (-12)'
    elif '多头排列' in macd_cross:
        macd_score = 6 if macd_above_zero else 3
        macd_desc = f'多头排列+零轴{"上" if macd_above_zero else "下"} ({macd_score:+d})'
    else:
        macd_score = -6 if not macd_above_zero else -3
        macd_desc = f'空头排列+零轴{"下" if not macd_above_zero else "上"} ({macd_score:+d})'
    signals['MACD'] = (macd_score, macd_desc)

    # CMF (10分)
    cmf = _cmf(df_24h)
    cmf_val = cmf.dropna().iloc[-1] if not cmf.dropna().empty else 0
    if cmf_val > 0.05:
        cmf_score = min(10, round(cmf_val * 100))
    elif cmf_val < -0.05:
        cmf_score = max(-10, round(cmf_val * 100))
    else:
        cmf_score = 0
    signals['CMF'] = (cmf_score, f'值 {cmf_val:.3f} ({cmf_score:+d})')

    # VWAP (8分)
    vwap = _vwap(df_24h)
    vwap_val = vwap.iloc[-1]
    vwap_score = 8 if close > vwap_val else -8
    signals['VWAP'] = (vwap_score,
                       f'价格{"上方" if vwap_score > 0 else "下方"} ({vwap_score:+d})')

    # ── 情绪极值 (20分) ──────────────────────────────────
    # RSI 背离 (12分)
    rsi = _rsi(df_24h)
    rsi_val = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
    rsi_div = divergence_detect(df_24h['close'], rsi.dropna())
    if '底背离' in rsi_div:
        rsi_div_score = 12
    elif '顶背离' in rsi_div:
        rsi_div_score = -12
    else:
        rsi_div_score = 0
    signals['RSI背离'] = (rsi_div_score, f'{rsi_div} ({rsi_div_score:+d})')

    # RSI 极值 (5分)
    if rsi_val < 30:
        rsi_ext_score = 5
        rsi_ext_desc = f'超卖 {rsi_val:.1f} (+5)'
    elif rsi_val > 70:
        rsi_ext_score = -5
        rsi_ext_desc = f'超买 {rsi_val:.1f} (-5)'
    else:
        rsi_ext_score = 0
        rsi_ext_desc = f'中性 {rsi_val:.1f} (0)'
    signals['RSI极值'] = (rsi_ext_score, rsi_ext_desc)

    # Williams %R (3分)
    wr = _williams_r(df_24h)
    wr_val = wr.dropna().iloc[-1] if not wr.dropna().empty else -50
    if wr_val < -80:
        wr_score = 3
    elif wr_val > -20:
        wr_score = -3
    else:
        wr_score = 0
    signals['Williams%R'] = (wr_score, f'{wr_val:.1f} ({wr_score:+d})')

    # ── 宏观背景 (15分) ──────────────────────────────────
    macro_score = 0
    macro_descs = []
    if not df_daily.empty and len(df_daily) >= 50:
        daily_close = df_daily['close'].iloc[-1]

        # MA200 (10分)
        ma200 = df_daily['close'].rolling(200).mean().dropna()
        if not ma200.empty:
            m200_score = 10 if daily_close > ma200.iloc[-1] else -10
            macro_score += m200_score
            macro_descs.append(f'MA200{"↑" if m200_score > 0 else "↓"}({m200_score:+d})')

        # MA50 (5分)
        ma50 = df_daily['close'].rolling(50).mean().dropna()
        if not ma50.empty:
            m50_score = 5 if daily_close > ma50.iloc[-1] else -5
            macro_score += m50_score
            macro_descs.append(f'MA50{"↑" if m50_score > 0 else "↓"}({m50_score:+d})')
    signals['宏观均线'] = (macro_score, ', '.join(macro_descs) if macro_descs else '数据不足')

    # ── 市场状态修正 ──────────────────────────────────────
    chop = _chop(df_24h)
    chop_val = chop.dropna().iloc[-1] if not chop.dropna().empty else 50
    if chop_val < 38.2:
        modifier = 1.2
        market_state = f'趋势市 ({chop_val:.1f}) × 1.2'
    elif chop_val > 61.8:
        modifier = 0.7
        market_state = f'震荡市 ({chop_val:.1f}) × 0.7'
    else:
        modifier = 1.0
        market_state = f'过渡状态 ({chop_val:.1f}) × 1.0'

    raw_score = sum(s for s, _ in signals.values())
    final_score = int(np.clip(raw_score * modifier, -100, 100))

    return final_score, signals, market_state, chop_val, vwap_val, rsi_val


# ==========================================
# 止损/止盈计算
# ==========================================

def _calc_stops(df_24h, close, direction, vwap_val):
    """
    计算四种止损方法，返回 dict。
    direction: 1=做多, -1=做空

    止损方法:
    ① ATR止损     — 价格 ± 2×ATR，动态跟随波动率
    ② 结构止损    — SuperTrend轨道 + 近期摆动极值 + 0.3×ATR缓冲
    ③ VWAP止损    — VWAP ± 0.2×ATR，基于机构成本线
    ④ 百分比止损  — 固定 1% / 2% / 3%，简单易执行
    """
    atr_val = _atr(df_24h).dropna()
    atr = float(atr_val.iloc[-1]) if not atr_val.empty else close * 0.01
    atr_mean = float(atr_val.mean()) if not atr_val.empty else atr

    st, st_trend, st_upper, st_lower = _supertrend(df_24h)
    st_val_series = st.dropna()
    st_line = float(st_val_series.iloc[-1]) if not st_val_series.empty else close

    st_lower_clean = st_lower.dropna()
    st_upper_clean = st_upper.dropna()
    st_lower_val = float(st_lower_clean.iloc[-1]) if not st_lower_clean.empty else close - 2 * atr
    st_upper_val = float(st_upper_clean.iloc[-1]) if not st_upper_clean.empty else close + 2 * atr

    # 近期摆动低/高点 (过去 20 根 K 线)
    recent = df_24h.tail(20)
    swing_low = float(recent['low'].min())
    swing_high = float(recent['high'].max())

    if direction == 1:  # 做多
        sl_atr = round(close - 2 * atr, 4)
        sl_structure = round(min(st_lower_val, swing_low) - atr * 0.3, 4)
        sl_vwap = round(vwap_val - atr * 0.2, 4) if vwap_val < close else None
        sl_pct = {pct: round(close * (1 - pct), 4) for pct in (0.01, 0.02, 0.03)}
    else:  # 做空
        sl_atr = round(close + 2 * atr, 4)
        sl_structure = round(max(st_upper_val, swing_high) + atr * 0.3, 4)
        sl_vwap = round(vwap_val + atr * 0.2, 4) if vwap_val > close else None
        sl_pct = {pct: round(close * (1 + pct), 4) for pct in (0.01, 0.02, 0.03)}

    return {
        'atr': atr,
        'atr_mean': atr_mean,
        'sl_atr': sl_atr,
        'sl_structure': sl_structure,
        'sl_vwap': sl_vwap,
        'sl_pct': sl_pct,
        'swing_low': swing_low,
        'swing_high': swing_high,
        'st_line': st_line,
        'st_lower': st_lower_val,
        'st_upper': st_upper_val,
    }


def _calc_entry_zones(close, direction, vwap_val, stops):
    """
    计算三种入场策略的具体价格区间。

    ① 市价入场   — 当前价格立即执行，适合信号极强
    ② 回踩入场   — 等待价格回踩 VWAP / SuperTrend 支撑，风险更低
    ③ 突破入场   — 确认突破近期高/低点后入场，可靠性最高
    """
    atr = stops['atr']
    zones = []

    if direction == 1:
        # ① 市价
        zones.append(('市价入场', close,
                       f'当前价 {close:.4f}，立即执行',
                       '适合: 评分 ≥65 + 趋势市，信号极强时'))
        # ② 回踩支撑
        support = max(vwap_val, stops['st_lower'])
        pullback = round(support + atr * 0.1, 4)
        zones.append(('回踩入场', pullback,
                       f'回踩至 max(VWAP {vwap_val:.4f}, ST下轨 {stops["st_lower"]:.4f}) + 缓冲 = {pullback:.4f}',
                       '适合: 中等信号，等待价格回调验证支撑'))
        # ③ 突破
        breakout = round(stops['swing_high'] * 1.001, 4)
        zones.append(('突破入场', breakout,
                       f'突破近20根高点 {stops["swing_high"]:.4f} +0.1% = {breakout:.4f}',
                       '适合: 放量突破确认，避免假突破'))
    else:
        # ① 市价
        zones.append(('市价入场', close,
                       f'当前价 {close:.4f}，立即执行',
                       '适合: 评分 ≤-65 + 趋势市，信号极强时'))
        # ② 反弹阻力
        resistance = min(vwap_val, stops['st_upper'])
        pullback = round(resistance - atr * 0.1, 4)
        zones.append(('反弹做空', pullback,
                       f'反弹至 min(VWAP {vwap_val:.4f}, ST上轨 {stops["st_upper"]:.4f}) - 缓冲 = {pullback:.4f}',
                       '适合: 中等信号，等待反弹验证阻力'))
        # ③ 跌破
        breakdown = round(stops['swing_low'] * 0.999, 4)
        zones.append(('跌破入场', breakdown,
                       f'跌破近20根低点 {stops["swing_low"]:.4f} -0.1% = {breakdown:.4f}',
                       '适合: 放量跌破确认，避免假跌破'))

    return zones


def _dynamic_rr(chop_val, atr_current, atr_mean):
    """
    根据市场状态动态调整 R/R 目标比例。

    趋势市 (CHOP < 38.2): 目标可设远 → 1.5 / 3.0 / 5.0
    震荡市 (CHOP > 61.8): 目标需保守 → 0.8 / 1.5 / 2.5
    过渡期 (38.2~61.8):   标准设置   → 1.0 / 2.0 / 3.5

    ATR相对于均值的偏离也会调整倍数:
    - ATR 高 (>1.5x均值): ×0.85，波动大，远目标难以到达
    - ATR 低 (<0.7x均值): ×1.15，波动小，趋势更流畅
    """
    if chop_val < 38.2:
        base = (1.5, 3.0, 5.0)
        state_desc = f'趋势市 ({chop_val:.1f}) → 目标可设远'
    elif chop_val > 61.8:
        base = (0.8, 1.5, 2.5)
        state_desc = f'震荡市 ({chop_val:.1f}) → 目标需保守'
    else:
        base = (1.0, 2.0, 3.5)
        state_desc = f'过渡期 ({chop_val:.1f}) → 标准设置'

    # ATR 调整因子
    atr_ratio = atr_current / atr_mean if atr_mean > 0 else 1.0
    if atr_ratio > 1.5:
        atr_mod = 0.85
        atr_note = f'ATR {atr_ratio:.1f}x均值 (高波动) → ×0.85'
    elif atr_ratio < 0.7:
        atr_mod = 1.15
        atr_note = f'ATR {atr_ratio:.1f}x均值 (低波动) → ×1.15'
    else:
        atr_mod = 1.0
        atr_note = f'ATR {atr_ratio:.1f}x均值 (正常) → ×1.0'

    ratios = tuple(round(r * atr_mod, 1) for r in base)
    return ratios, state_desc, atr_note


def _calc_targets(close, sl, direction, rr_ratios=(1.0, 2.0, 3.0)):
    """
    根据止损距离和 R/R 比计算止盈目标。
    """
    risk = abs(close - sl)
    targets = []
    for rr in rr_ratios:
        tp = round(close + risk * rr, 4) if direction == 1 else round(close - risk * rr, 4)
        pct = abs(tp - close) / close * 100
        targets.append((tp, rr, pct))
    return targets


# ==========================================
# 主函数
# ==========================================

def entry_signal(symbol: str, optional_symbol: str | None = None) -> str:
    """
    主函数: 多维度加权评分，输出入场信号与风控建议。

    输入:
        symbol: 主标的代码 (如 'AAPL', 'BTC')
        optional_symbol: 暂未使用，预留对比接口

    输出:
        str: LLM 可读的综合入场分析报告
    """
    df = load_bars(symbol)
    if df.empty:
        return f"无法获取 {symbol} 的数据"

    df_24h = get_recent_24h(df)
    if len(df_24h) < 30:
        df_24h = df.tail(96)

    df_daily = resample_daily(df)
    close = float(df_24h['close'].iloc[-1])

    # ── 评分 ─────────────────────────────────────────────
    final_score, signals, market_state, chop_val, vwap_val, rsi_val = \
        _score_signals(df_24h, df_daily)

    # ── 方向判断 ──────────────────────────────────────────
    if final_score >= 40:
        direction = 1
        direction_str = '做多 (LONG)'
        confidence = '高' if final_score >= 65 else '中'
    elif final_score <= -40:
        direction = -1
        direction_str = '做空 (SHORT)'
        confidence = '高' if final_score <= -65 else '中'
    else:
        direction = 0
        direction_str = '观望 (WAIT)'
        confidence = '低'

    # ── 止损/止盈 ─────────────────────────────────────────
    sections = []

    # 评分概览
    bull_count = sum(1 for s, _ in signals.values() if s > 0)
    bear_count = sum(1 for s, _ in signals.values() if s < 0)
    sections.append(('综合评分', f'{final_score:+d} / ±100  '
                                 f'(看多信号 {bull_count}个, 看空信号 {bear_count}个)'))
    sections.append(('置信度', f'{confidence}  |  市场状态: {market_state}'))
    sections.append(('方向建议', direction_str))
    sections.append(('当前价格', f'{close}'))

    # 各信号明细
    detail_lines = []
    for name, (score, desc) in signals.items():
        mark = '▲' if score > 0 else ('▼' if score < 0 else '─')
        detail_lines.append(f'{mark} {name}: {desc}')
    sections.append(('信号明细', '\n  ' + '\n  '.join(detail_lines)))

    if direction != 0:
        stops = _calc_stops(df_24h, close, direction, vwap_val)
        atr = stops['atr']

        # ── 入场区间 (三种策略) ───────────────────────────
        zones = _calc_entry_zones(close, direction, vwap_val, stops)
        zone_lines = []
        for name, price, detail, advice in zones:
            zone_lines.append(f'【{name}】 @ {price:.4f}')
            zone_lines.append(f'   价格: {detail}')
            zone_lines.append(f'   适用: {advice}')
        sections.append(('入场区间', '\n  ' + '\n  '.join(zone_lines)))

        # ── 四种止损方法 ─────────────────────────────────
        sl_methods = []
        sl_atr_pct = abs(close - stops['sl_atr']) / close * 100
        sl_struct_pct = abs(close - stops['sl_structure']) / close * 100
        sl_methods.append(f"① ATR止损:     {stops['sl_atr']:.4f}  (风险 -{sl_atr_pct:.2f}%, 基于 2×ATR={atr:.4f})")
        sl_methods.append(f"② 结构止损:    {stops['sl_structure']:.4f}  "
                          f"(ST{'下轨' if direction == 1 else '上轨'}{stops['st_lower' if direction == 1 else 'st_upper']:.4f}"
                          f" + 摆动极值 + 缓冲, 风险 -{sl_struct_pct:.2f}%) ← 推荐")
        if stops['sl_vwap'] is not None:
            sl_vwap_pct = abs(close - stops['sl_vwap']) / close * 100
            sl_methods.append(f"③ VWAP止损:    {stops['sl_vwap']:.4f}  (VWAP {vwap_val:.4f} 下方缓冲, 风险 -{sl_vwap_pct:.2f}%)")
        else:
            sl_methods.append(f"③ VWAP止损:    不适用 (价格已{'低于' if direction == 1 else '高于'} VWAP)")
        pct_sl = stops['sl_pct']
        sl_methods.append(f"④ 百分比止损:  1%={pct_sl[0.01]:.4f}  |  2%={pct_sl[0.02]:.4f}  |  3%={pct_sl[0.03]:.4f}")
        sections.append(('止损方案 (四选一)', '\n  ' + '\n  '.join(sl_methods)))

        # ── 动态止盈目标 (基于结构止损 + 动态 R/R) ────────
        rr_ratios, rr_state, rr_atr_note = _dynamic_rr(chop_val, atr, stops['atr_mean'])
        sl_for_tp = stops['sl_structure']
        targets = _calc_targets(close, sl_for_tp, direction, rr_ratios=rr_ratios)
        tp_lines = [f'依据: {rr_state}, {rr_atr_note}']
        for i, (tp, rr, pct) in enumerate(targets, 1):
            tp_lines.append(f'T{i}: {tp:.4f}  '
                            f'({"+" if direction == 1 else "-"}{pct:.2f}%,  R/R = 1:{rr})')
        sections.append(('止盈目标 (动态R/R)', '\n  ' + '\n  '.join(tp_lines)))

        # ── 参考价格 ─────────────────────────────────────
        sections.append(('关键价格参考',
                         f'当前: {close:.4f}  |  VWAP: {vwap_val:.4f}  |  ATR: {atr:.4f}\n  '
                         f'ST下轨: {stops["st_lower"]:.4f}  |  ST上轨: {stops["st_upper"]:.4f}\n  '
                         f'近20根低点: {stops["swing_low"]:.4f}  |  近20根高点: {stops["swing_high"]:.4f}'))

        # ── 注意事项 ─────────────────────────────────────
        warnings = []
        if chop_val > 61.8:
            warnings.append('⚠ 震荡市，信号可靠性下降，建议缩小仓位或使用百分比止损')
        if abs(final_score) < 60 and confidence == '中':
            warnings.append('⚠ 评分处于中等区间，建议等待回踩入场而非市价追入')
        if rsi_val > 70 and direction == 1:
            warnings.append('⚠ RSI超买，做多建议等待回踩入场，勿追高')
        if rsi_val < 30 and direction == -1:
            warnings.append('⚠ RSI超卖，做空建议等待反弹入场，勿追空')
        if sl_struct_pct > 5:
            warnings.append(f'⚠ 结构止损距离 {sl_struct_pct:.1f}% 偏大，可考虑 ATR 或百分比止损替代')
        if warnings:
            sections.append(('注意事项', '\n  '.join(warnings)))
    else:
        sections.append(('建议', f'评分 {final_score:+d} 处于观望区间 (-40 ~ +40)，'
                                  '等待多维度信号一致后再入场'))

    return format_report(f"{symbol} 入场信号分析", sections)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Entry Signal - 入场信号聚合与风控")
    parser.add_argument("symbol", help="股票/虚拟货币代码 (如 AAPL, BTC)")
    args = parser.parse_args()
    print(entry_signal(args.symbol))
