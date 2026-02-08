"""
votality_risk.py - 风控与波动率分析

指标: Keltner Channels, Volatility Squeeze, CHOP (Choppiness Index)
核心思想: 波动率是"风险的代名词"。
         低波动率 = 暴风雨前的宁静 (即将变盘)，
         高波动率 = 暴风雨正在进行 (趋势已启动)。
         CHOP 指数区分"趋势市"和"震荡市"，帮助选择策略。
"""

import pandas as pd
import numpy as np
from .calculate import (
    load_bars, get_recent_24h,
    above_below, trend_direction, classify_level,
    range_position, compare_symbols, format_report,
    sigma_position, rate_of_change
)


def calculate_keltner_channels(data: pd.DataFrame, period: int = 20,
                               atr_mult: int = 2) -> pd.DataFrame:
    """
    计算肯特纳通道 (Keltner Channels)。
    LLM 逻辑:
    - 相比布林带(基于标准差)，肯特纳基于 ATR。
    - 它对洗盘不敏感，过滤假突破更好。
    - 价格 > Upper: 真正的强势突破。
    - 价格 < Lower: 真正的弱势跌破。
    """
    ema = data['close'].ewm(span=period, adjust=False).mean()

    high, low, close = data['high'], data['low'], data['close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(10).mean()

    upper = ema + (atr * atr_mult)
    lower = ema - (atr * atr_mult)

    pos = (data['close'] - lower) / (upper - lower).replace(0, 0.001)

    return pd.DataFrame({
        'kc_upper': upper,
        'kc_lower': lower,
        'kc_mid': ema,
        'kc_position': pos
    })


def calculate_volatility_squeeze(data: pd.DataFrame, bb_period: int = 20,
                                 bb_mult: float = 2.0, kc_period: int = 20,
                                 kc_mult: float = 1.5) -> pd.DataFrame:
    """
    计算"挤牌"信号 (TTM Squeeze)。
    LLM 逻辑:
    - 当布林带收窄进肯特纳通道内时，代表波动率极度压缩。
    - Squeeze On (True): 暴风雨前的宁静，即将变盘，LLM 应提示"等待突破"。
    - Squeeze Off: 能量已释放，趋势已启动。
    - Momentum > 0: 突破方向向上。
    - Momentum < 0: 突破方向向下。
    """
    close = data['close']

    # 布林带
    bb_mid = close.rolling(bb_period).mean()
    bb_std = close.rolling(bb_period).std()
    bb_upper = bb_mid + bb_mult * bb_std
    bb_lower = bb_mid - bb_mult * bb_std

    # 肯特纳通道
    high, low = data['high'], data['low']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(kc_period).mean()
    kc_ema = close.ewm(span=kc_period, adjust=False).mean()
    kc_upper = kc_ema + kc_mult * atr
    kc_lower = kc_ema - kc_mult * atr

    # Squeeze: BB 完全在 KC 内部
    squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

    # 动量 (线性回归的值作为方向参考)
    momentum = close - close.rolling(bb_period).mean()

    return pd.DataFrame({
        'squeeze_on': squeeze_on,
        'squeeze_momentum': momentum,
        'bb_width': (bb_upper - bb_lower) / bb_mid
    })


def calculate_chop(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算 Choppiness Index (CHOP 指数)。
    LLM 逻辑:
    - CHOP 范围: 0-100。
    - CHOP > 61.8: 震荡市 (Choppy)，不适合趋势跟踪策略，
      应使用均值回归/网格交易。
    - CHOP < 38.2: 趋势市 (Trending)，适合趋势跟踪策略，
      使用均线/突破策略。
    - 从高位下降: 震荡期结束，新趋势即将启动。
    - 从低位上升: 趋势衰竭，即将进入震荡。
    """
    high, low, close = data['high'], data['low'], data['close']

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    atr_sum = tr.rolling(window=period).sum()
    high_max = high.rolling(window=period).max()
    low_min = low.rolling(window=period).min()

    hl_range = (high_max - low_min).replace(0, 0.001)
    chop = 100 * np.log10(atr_sum / hl_range) / np.log10(period)

    return chop


def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算平均真实波幅 (ATR)。
    LLM 逻辑:
    - ATR 扩大: 波动加剧，趋势强劲或恐慌蔓延。
    - ATR 缩小: 波动收敛，市场在盘整。
    - 止损建议: 当前价格 ± 2*ATR。
    """
    high, low, close = data['high'], data['low'], data['close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def volatility_risk(symbol: str, optional_symbol: str = None) -> str:
    """
    主函数: 风控与波动率分析。

    输入:
        symbol: 主标的代码 (如 'AAPL')
        optional_symbol: 可选对比标的 (如 'SPY')

    输出:
        str: LLM 可读的风控与波动率报告
    """
    df = load_bars(symbol)
    if df.empty:
        return f"无法获取 {symbol} 的数据"

    df_24h = get_recent_24h(df)
    if len(df_24h) < 20:
        df_24h = df.tail(96)

    close = df_24h['close'].iloc[-1]

    # --- Keltner Channels ---
    kc = calculate_keltner_channels(df_24h)
    kc_pos = kc['kc_position'].dropna().iloc[-1] if not kc['kc_position'].dropna().empty else 0.5
    kc_upper = kc['kc_upper'].dropna().iloc[-1] if not kc['kc_upper'].dropna().empty else close
    kc_lower = kc['kc_lower'].dropna().iloc[-1] if not kc['kc_lower'].dropna().empty else close

    kc_pos_desc = range_position(close, kc_lower, kc_upper)
    if kc_pos > 1.0:
        kc_signal = "突破上轨 (强势突破)"
    elif kc_pos < 0.0:
        kc_signal = "跌破下轨 (弱势跌破)"
    else:
        kc_signal = f"通道内 ({kc_pos_desc})"

    # --- Volatility Squeeze ---
    squeeze = calculate_volatility_squeeze(df_24h)
    sq_on = squeeze['squeeze_on'].dropna()
    sq_mom = squeeze['squeeze_momentum'].dropna()

    if not sq_on.empty:
        is_squeeze = sq_on.iloc[-1]
        squeeze_count = sq_on.tail(10).sum()  # 最近 10 根 K 线中有多少根处于 Squeeze
        if is_squeeze:
            sq_signal = f"Squeeze ON (波动率压缩中，最近10根有{int(squeeze_count)}根Squeeze)"
        else:
            sq_signal = "Squeeze OFF (能量已释放)"

        if not sq_mom.empty:
            mom_val = sq_mom.iloc[-1]
            mom_dir = "向上" if mom_val > 0 else "向下"
            mom_trend = trend_direction(sq_mom)
            sq_signal += f", 动量方向: {mom_dir}, 动量趋势: {mom_trend}"
    else:
        sq_signal = "数据不足"

    # --- CHOP ---
    chop = calculate_chop(df_24h)
    chop_current = chop.dropna().iloc[-1] if not chop.dropna().empty else 50
    chop_level = classify_level(chop_current, {
        '强震荡': 61.8, '弱震荡': 50, '弱趋势': 38.2, '强趋势': 0
    })
    chop_trend = trend_direction(chop.dropna())
    chop_roc = rate_of_change(chop.dropna(), 3)

    if chop_current > 61.8:
        chop_advice = "震荡市 → 建议: 均值回归/网格策略，避免追涨杀跌"
    elif chop_current < 38.2:
        chop_advice = "趋势市 → 建议: 趋势跟踪/突破策略"
    else:
        chop_advice = "过渡状态 → 观望，等待明确信号"

    # --- ATR ---
    atr = calculate_atr(df_24h)
    atr_current = atr.dropna().iloc[-1] if not atr.dropna().empty else 0
    atr_mean = atr.dropna().mean() if not atr.dropna().empty else 1
    atr_std = atr.dropna().std() if not atr.dropna().empty else 1
    atr_sigma = sigma_position(atr_current, atr_mean, atr_std)
    atr_trend = trend_direction(atr.dropna())
    stop_loss = f"建议止损距离: ±{atr_current * 2:.2f} (2×ATR)"

    sections = [
        ("Keltner通道", f"信号: {kc_signal}, "
                       f"价格距上轨: {above_below(close, kc_upper, '价格', '上轨')}, "
                       f"价格距下轨: {above_below(close, kc_lower, '价格', '下轨')}"),
        ("Squeeze", sq_signal),
        ("CHOP", f"水平: {chop_level} ({chop_current:.1f}), "
                f"趋势: {chop_trend}, 变化: {chop_roc}, {chop_advice}"),
        ("ATR", f"波动水平: {atr_sigma}, 趋势: {atr_trend}, {stop_loss}"),
    ]

    report = format_report(f"{symbol} 风控与波动率分析", sections)

    if optional_symbol:
        df_opt = load_bars(optional_symbol)
        if not df_opt.empty:
            df_opt_24h = get_recent_24h(df_opt)
            if len(df_opt_24h) < 20:
                df_opt_24h = df_opt.tail(96)

            chop_opt = calculate_chop(df_opt_24h).dropna()
            atr_opt = calculate_atr(df_opt_24h).dropna()
            if not chop_opt.empty and not atr_opt.empty:
                report += "\n--- 对比 ---"
                report += f"\n{compare_symbols(chop_current, chop_opt.iloc[-1], symbol, optional_symbol, 'CHOP')}"
                # ATR 用百分比 (相对于价格) 比较更公平
                atr_pct_a = atr_current / close * 100
                opt_close = df_opt_24h['close'].iloc[-1]
                atr_pct_b = atr_opt.iloc[-1] / opt_close * 100
                report += f"\n{compare_symbols(atr_pct_a, atr_pct_b, symbol, optional_symbol, 'ATR%')}"

    return report
