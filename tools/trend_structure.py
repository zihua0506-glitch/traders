from __future__ import annotations

"""
trend_structure.py - 确定当前的市场背景 (Context)

指标: 一目均衡表 (Ichimoku), SuperTrend, 抛物线 SAR (Parabolic SAR)
核心思想: 先判断大环境是多头还是空头，再决定操作方向。
         "顺势而为" —— 只在上升趋势中做多，只在下降趋势中做空。
"""

import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools.calculate import (
    load_bars, get_recent_24h, resample_daily,
    above_below, trend_direction, cross_detect,
    format_report, support_resistance_relation,
    multi_timeframe_alignment
)


def calculate_ichimoku_baseline(data: pd.DataFrame) -> pd.DataFrame:
    """
    计算一目均衡表 (Ichimoku) 的基准线和转换线。
    LLM 逻辑:
    - Conversion (Tenkan): 短期趋势。
    - Base (Kijun): 中期趋势，也是重要防守位。
    - 价格 > Base Line: 多头市场。
    - Conversion 上穿 Base: 强力买入信号 (TK Cross)。
    """
    high_9 = data['high'].rolling(window=9).max()
    low_9 = data['low'].rolling(window=9).min()
    tenkan_sen = (high_9 + low_9) / 2

    high_26 = data['high'].rolling(window=26).max()
    low_26 = data['low'].rolling(window=26).min()
    kijun_sen = (high_26 + low_26) / 2

    return pd.DataFrame({'ichimoku_conv': tenkan_sen, 'ichimoku_base': kijun_sen})


def calculate_parabolic_sar(data: pd.DataFrame, af_start: float = 0.02,
                            af_step: float = 0.02, af_max: float = 0.2) -> pd.DataFrame:
    """
    计算抛物线指标 (Parabolic SAR)。
    LLM 逻辑:
    - SAR 点在价格下方: 处于上涨行情，持有。
    - SAR 点跳到价格上方: 趋势反转，立即离场/做空。
    - 对于短线预测，SAR 的反转是最灵敏的警报。
    """
    high = data['high'].values
    low = data['low'].values
    n = len(data)

    sar = np.zeros(n)
    trend = np.ones(n)  # 1 = 上升, -1 = 下降
    af = af_start
    ep = high[0]  # extreme point

    sar[0] = low[0]

    for i in range(1, n):
        if trend[i-1] == 1:  # 上升趋势
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = min(sar[i], low[i-1], low[max(0, i-2)])

            if low[i] < sar[i]:  # 反转为下降
                trend[i] = -1
                sar[i] = ep
                ep = low[i]
                af = af_start
            else:
                trend[i] = 1
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + af_step, af_max)
        else:  # 下降趋势
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = max(sar[i], high[i-1], high[max(0, i-2)])

            if high[i] > sar[i]:  # 反转为上升
                trend[i] = 1
                sar[i] = ep
                ep = high[i]
                af = af_start
            else:
                trend[i] = -1
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + af_step, af_max)

    return pd.DataFrame({
        'sar': sar,
        'sar_trend': trend  # 1=上升(支撑在下), -1=下降(阻力在上)
    }, index=data.index)


def calculate_supertrend(data: pd.DataFrame, period: int = 10,
                         multiplier: float = 3) -> pd.DataFrame:
    """
    计算超级趋势 (SuperTrend)。
    LLM 逻辑:
    - Close > SuperTrend: 只做多。
    - Close < SuperTrend: 只做空。
    - 它是趋势跟踪的最强过滤器。
    """
    high, low, close = data['high'], data['low'], data['close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    hl2 = (high + low) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    n = len(data)
    upper = basic_upper.copy()
    lower = basic_lower.copy()
    st_trend = pd.Series(np.ones(n), index=data.index)

    for i in range(1, n):
        # 更新上轨: 取较小值 (收紧)
        if basic_upper.iloc[i] < upper.iloc[i-1] or close.iloc[i-1] > upper.iloc[i-1]:
            upper.iloc[i] = basic_upper.iloc[i]
        else:
            upper.iloc[i] = upper.iloc[i-1]

        # 更新下轨: 取较大值 (收紧)
        if basic_lower.iloc[i] > lower.iloc[i-1] or close.iloc[i-1] < lower.iloc[i-1]:
            lower.iloc[i] = basic_lower.iloc[i]
        else:
            lower.iloc[i] = lower.iloc[i-1]

        # 判断趋势方向
        if st_trend.iloc[i-1] == 1:
            if close.iloc[i] < lower.iloc[i]:
                st_trend.iloc[i] = -1
            else:
                st_trend.iloc[i] = 1
        else:
            if close.iloc[i] > upper.iloc[i]:
                st_trend.iloc[i] = 1
            else:
                st_trend.iloc[i] = -1

    supertrend = pd.Series(
        np.where(st_trend == 1, lower, upper),
        index=data.index
    )

    return pd.DataFrame({
        'supertrend': supertrend,
        'st_trend': st_trend,  # 1=多头, -1=空头
        'st_upper': upper,
        'st_lower': lower
    })


def trend_structure(symbol: str, optional_symbol: str | None = None) -> str:
    """
    主函数: 确定当前的市场背景。

    输入:
        symbol: 主标的代码
        optional_symbol: 可选对比标的

    输出:
        str: LLM 可读的市场结构分析报告
    """
    df = load_bars(symbol)
    if df.empty:
        return f"无法获取 {symbol} 的数据"

    # 微观: 24h 15min 数据
    df_24h = get_recent_24h(df)
    if len(df_24h) < 30:
        df_24h = df.tail(96)

    # 宏观: 日线 (从 15min 聚合)
    df_daily = resample_daily(df)

    close = df_24h['close'].iloc[-1]

    # --- Ichimoku (微观) ---
    ichimoku = calculate_ichimoku_baseline(df_24h)
    conv = ichimoku['ichimoku_conv'].dropna()
    base = ichimoku['ichimoku_base'].dropna()

    ichi_price_vs_base = above_below(close, base.iloc[-1], "价格", "基准线(Kijun)")
    ichi_tk_cross = cross_detect(conv, base)
    ichi_conv_trend = trend_direction(conv)

    # --- Ichimoku (宏观) ---
    macro_signal = "数据不足"
    if len(df_daily) >= 26:
        ichimoku_d = calculate_ichimoku_baseline(df_daily)
        base_d = ichimoku_d['ichimoku_base'].dropna()
        if not base_d.empty:
            daily_close = df_daily['close'].iloc[-1]
            macro_signal = "多头" if daily_close > base_d.iloc[-1] else "空头"

    # --- SuperTrend ---
    st_data = calculate_supertrend(df_24h)
    st_current = st_data['supertrend'].iloc[-1]
    st_trend_val = st_data['st_trend'].iloc[-1]
    st_signal = "多头 (价格在 SuperTrend 上方)" if st_trend_val == 1 else \
                "空头 (价格在 SuperTrend 下方)"
    st_distance = above_below(close, st_current, "价格", "SuperTrend")

    # --- Parabolic SAR ---
    sar_data = calculate_parabolic_sar(df_24h)
    sar_trend_val = sar_data['sar_trend'].iloc[-1]
    sar_signal = "上升趋势 (SAR支撑在下)" if sar_trend_val == 1 else \
                 "下降趋势 (SAR阻力在上)"
    sar_current = sar_data['sar'].iloc[-1]
    sar_distance = above_below(close, sar_current, "价格", "SAR")

    # --- 多周期一致性 ---
    micro_signal = st_signal
    alignment = multi_timeframe_alignment(micro_signal, f"日线 {macro_signal}")

    # --- 支撑/阻力 ---
    support = st_data['st_lower'].iloc[-1]
    resistance = st_data['st_upper'].iloc[-1]
    sr_desc = support_resistance_relation(close, support, resistance)

    sections = [
        ("Ichimoku", f"{ichi_price_vs_base}, TK交叉: {ichi_tk_cross}, "
                     f"转换线趋势: {ichi_conv_trend}"),
        ("SuperTrend", f"信号: {st_signal}, {st_distance}"),
        ("SAR", f"信号: {sar_signal}, {sar_distance}"),
        ("支撑/阻力", sr_desc),
        ("多周期", f"微观: {micro_signal}, 宏观: {macro_signal}, "
                  f"一致性: {alignment}"),
    ]

    report = format_report(f"{symbol} 市场结构分析", sections)

    if optional_symbol:
        df_opt = load_bars(optional_symbol)
        if not df_opt.empty:
            df_opt_24h = get_recent_24h(df_opt)
            if len(df_opt_24h) < 30:
                df_opt_24h = df_opt.tail(96)
            st_opt = calculate_supertrend(df_opt_24h)
            st_opt_trend = st_opt['st_trend'].iloc[-1]
            report += "\n--- 对比 ---"
            report += f"\n{symbol} SuperTrend: {'多头' if st_trend_val == 1 else '空头'}"
            report += f"\n{optional_symbol} SuperTrend: {'多头' if st_opt_trend == 1 else '空头'}"

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trend Structure - 市场趋势结构分析")
    parser.add_argument("symbol", help="股票/虚拟货币代码 (如 AAPL, BTC)")
    parser.add_argument("--vs", dest="optional_symbol", default=None,
                        help="对比标的 (如 SPY)")
    args = parser.parse_args()
    print(trend_structure(args.symbol, args.optional_symbol))
