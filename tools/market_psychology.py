"""
market_psychology.py - 捕捉人类交易者的非理性情绪（贪婪与恐慌），寻找反转点

指标: Williams %R, CCI (商品通道指数), RSI (相对强弱指数)
核心思想: 当市场情绪走向极端时 (极度贪婪或极度恐慌)，往往是反转的前兆。
         这些指标专门检测"情绪过热"状态。
"""

import pandas as pd
import numpy as np
from .calculate import (
    load_bars, get_recent_24h,
    above_below, trend_direction, classify_level,
    divergence_detect, compare_symbols, format_report,
    rate_of_change, extreme_detect
)


def calculate_williams_r(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算威廉指标 (Williams %R)。
    LLM 逻辑:
    - 范围: -100 到 0。
    - > -20: 超买区 (Overbought)，贪婪到极致，随时可能回调。
    - < -80: 超卖区 (Oversold)，恐慌到极致，反弹概率极大。
    - 从超买区快速下穿 -20: 卖出信号。
    - 从超卖区快速上穿 -80: 买入信号。
    """
    highest = data['high'].rolling(window=period).max()
    lowest = data['low'].rolling(window=period).min()
    wr = -100 * (highest - data['close']) / (highest - lowest).replace(0, 0.001)
    return wr


def calculate_cci(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算商品通道指数 (Commodity Channel Index, CCI)。
    LLM 逻辑:
    - CCI > +100: 超买，价格远高于统计平均。
    - CCI < -100: 超卖，价格远低于统计平均。
    - CCI > +200: 极端超买，崩盘风险。
    - CCI < -200: 极端超卖，恐慌性底部。
    - 从 +100 以上回落: 卖出信号。
    - 从 -100 以下反弹: 买入信号。
    """
    tp = (data['high'] + data['low'] + data['close']) / 3
    sma = tp.rolling(window=period).mean()
    mean_dev = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = (tp - sma) / (0.015 * mean_dev.replace(0, 0.001))
    return cci


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算相对强弱指数 (RSI)。
    LLM 逻辑:
    - RSI > 70: 超买，多头力量可能衰竭。
    - RSI < 30: 超卖，空头力量可能衰竭。
    - RSI 在 50 附近 = 多空平衡。
    - 顶背离 (价格新高 + RSI 未新高): 极强卖出信号。
    - 底背离 (价格新低 + RSI 未新低): 极强买入信号。
    """
    delta = data['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Wilder 平滑法 (EMA-like)
    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, 0.001)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def market_psychology(symbol: str, optional_symbol: str | None = None) -> str:
    """
    主函数: 捕捉市场非理性情绪，寻找反转点。

    输入:
        symbol: 主标的代码 (如 'AAPL')
        optional_symbol: 可选对比标的 (如 'SPY')

    输出:
        str: LLM 可读的情绪分析报告
    """
    df = load_bars(symbol)
    if df.empty:
        return f"无法获取 {symbol} 的数据"

    df_24h = get_recent_24h(df)
    if len(df_24h) < 20:
        df_24h = df.tail(96)

    # --- Williams %R ---
    wr = calculate_williams_r(df_24h)
    wr_current = wr.dropna().iloc[-1] if not wr.dropna().empty else -50
    wr_level = classify_level(wr_current, {
        '极度超买': -10, '超买': -20, '偏多': -40,
        '中性': -60, '超卖': -80, '极度超卖': -100
    })
    wr_trend = trend_direction(wr.dropna())
    wr_roc = rate_of_change(wr.dropna(), 3)

    # --- CCI ---
    cci = calculate_cci(df_24h)
    cci_current = cci.dropna().iloc[-1] if not cci.dropna().empty else 0
    cci_level = classify_level(cci_current, {
        '极端超买': 200, '超买': 100, '中性偏多': 0,
        '超卖': -100, '极端超卖': -200
    })
    # 注意: CCI 可以是负数，classify_level 按降序匹配
    if cci_current < -200:
        cci_level = '极端超卖'
    elif cci_current < -100:
        cci_level = '超卖'
    elif cci_current < 0:
        cci_level = '中性偏空'

    cci_trend = trend_direction(cci.dropna())
    cci_div = divergence_detect(df_24h['close'], cci.dropna())

    # --- RSI ---
    rsi = calculate_rsi(df_24h)
    rsi_current = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
    rsi_level = classify_level(rsi_current, {
        '严重超买': 80, '超买': 70, '偏多': 55,
        '中性': 45, '偏空': 30, '超卖': 20, '严重超卖': 0
    })
    rsi_trend = trend_direction(rsi.dropna())
    rsi_div = divergence_detect(df_24h['close'], rsi.dropna())

    # --- 综合情绪判断 ---
    overbought_count = sum([
        wr_current > -20,
        cci_current > 100,
        rsi_current > 70
    ])
    oversold_count = sum([
        wr_current < -80,
        cci_current < -100,
        rsi_current < 30
    ])

    if overbought_count >= 2:
        overall = "多指标共振超买 → 高度警惕回调"
    elif oversold_count >= 2:
        overall = "多指标共振超卖 → 高度关注反弹机会"
    elif overbought_count == 1:
        overall = "部分指标超买 → 适度谨慎"
    elif oversold_count == 1:
        overall = "部分指标超卖 → 观察企稳信号"
    else:
        overall = "情绪中性 → 无极端信号"

    # 背离汇总
    div_signals = []
    if "背离" in cci_div and "无" not in cci_div:
        div_signals.append(f"CCI {cci_div}")
    if "背离" in rsi_div and "无" not in rsi_div:
        div_signals.append(f"RSI {rsi_div}")
    div_summary = ", ".join(div_signals) if div_signals else "无背离信号"

    sections = [
        ("Williams%R", f"水平: {wr_level} ({wr_current:.1f}), "
                       f"趋势: {wr_trend}, 变化: {wr_roc}"),
        ("CCI", f"水平: {cci_level} ({cci_current:.1f}), "
               f"趋势: {cci_trend}, 背离: {cci_div}"),
        ("RSI", f"水平: {rsi_level} ({rsi_current:.1f}), "
               f"趋势: {rsi_trend}, 背离: {rsi_div}"),
        ("综合情绪", overall),
        ("背离汇总", div_summary),
    ]

    report = format_report(f"{symbol} 市场情绪分析", sections)

    if optional_symbol:
        df_opt = load_bars(optional_symbol)
        if not df_opt.empty:
            df_opt_24h = get_recent_24h(df_opt)
            if len(df_opt_24h) < 20:
                df_opt_24h = df_opt.tail(96)

            rsi_opt = calculate_rsi(df_opt_24h).dropna()
            cci_opt = calculate_cci(df_opt_24h).dropna()
            if not rsi_opt.empty and not cci_opt.empty:
                report += "\n--- 对比 ---"
                report += f"\n{compare_symbols(rsi_current, rsi_opt.iloc[-1], symbol, optional_symbol, 'RSI')}"
                report += f"\n{compare_symbols(cci_current, cci_opt.iloc[-1], symbol, optional_symbol, 'CCI')}"

    return report
