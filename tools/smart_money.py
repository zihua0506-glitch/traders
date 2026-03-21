from __future__ import annotations

"""
smart_money.py - 追踪机构资金流向，识别入场机会/价格波动

指标: VWAP, MFI, CMF, MACD
核心思想: 机构（聪明钱）的行为会在成交量和资金流指标中留下痕迹，
         通过跟踪这些痕迹来判断机构是在吸筹还是在出货。
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools.calculate import (
    load_bars, get_recent_24h,
    above_below, trend_direction, cross_detect,
    divergence_detect, classify_level, compare_symbols,
    format_report, rate_of_change
)


def calculate_vwap(data: pd.DataFrame) -> pd.Series:
    """
    计算成交量加权平均价 (VWAP)。
    LLM 逻辑:
    - 这是机构投资者的"平均成本线"，日内交易最重要的支撑/阻力位。
    - Price > VWAP: 多头控盘 (Bullish Control)，机构在推高价格。
    - Price < VWAP: 空头控盘 (Bearish Control)，机构在压低出货。
    - 价格回踩 VWAP 不破: 绝佳的买入点 (Support)。
    """
    v = data['volume']
    tp = (data['high'] + data['low'] + data['close']) / 3
    return (tp * v).cumsum() / v.cumsum()


def calculate_mfi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算资金流量指标 (MFI)。
    LLM 逻辑:
    - 也就是 "加了成交量权重的 RSI"。
    - MFI > 80: 资金严重超买，主力可能在诱多。
    - MFI < 20: 资金严重超卖，主力可能在恐慌中吸筹。
    - 顶背离: 股价创新高，但 MFI 下降 -> 此时上涨是虚的，即将暴跌。
    """
    tp = (data['high'] + data['low'] + data['close']) / 3
    raw_money_flow = tp * data['volume']

    positive_flow = []
    negative_flow = []

    for i in range(len(tp)):
        if i == 0:
            positive_flow.append(0)
            negative_flow.append(0)
            continue
        if tp.iloc[i] > tp.iloc[i-1]:
            positive_flow.append(raw_money_flow.iloc[i])
            negative_flow.append(0)
        elif tp.iloc[i] < tp.iloc[i-1]:
            positive_flow.append(0)
            negative_flow.append(raw_money_flow.iloc[i])
        else:
            positive_flow.append(0)
            negative_flow.append(0)

    pos_mf = pd.Series(positive_flow, index=data.index).rolling(period).sum()
    neg_mf = pd.Series(negative_flow, index=data.index).rolling(period).sum()

    mfi = 100 - (100 / (1 + pos_mf / neg_mf.replace(0, 0.001)))
    return mfi


def calculate_cmf(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算蔡金资金流 (Chaikin Money Flow)。
    LLM 逻辑:
    - 衡量资金进出的压力。
    - CMF > 0: 持续的买盘压力 (Accumulation)。
    - CMF < 0: 持续的卖盘压力 (Distribution)。
    - 如果价格横盘但 CMF 稳步上升，说明即将向上爆发。
    """
    mfm = ((data['close'] - data['low']) - (data['high'] - data['close'])) / \
          (data['high'] - data['low']).replace(0, 0.001)
    mfv = mfm * data['volume']
    cmf = mfv.rolling(period).sum() / data['volume'].rolling(period).sum()
    return cmf


def calculate_macd(data: pd.DataFrame, fast: int = 12, slow: int = 26,
                   signal: int = 9) -> pd.DataFrame:
    """
    计算 MACD (Moving Average Convergence Divergence)。
    LLM 逻辑:
    - MACD 线上穿信号线: 金叉 (买入信号)。
    - MACD 线下穿信号线: 死叉 (卖出信号)。
    - 柱状图 (Histogram) 由负转正: 空头动能衰竭，多头接管。
    - 零轴之上运行: 整体多头趋势。
    """
    ema_fast = data['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = data['close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    })


def smart_money(symbol: str, optional_symbol: str | None = None) -> str:
    """
    主函数: 追踪机构资金流向，识别入场机会。

    输入:
        symbol: 主标的代码 (如 'AAPL')
        optional_symbol: 可选对比标的 (如 'SPY')

    输出:
        str: LLM 可读的相对值分析报告
    """
    df = load_bars(symbol)
    if df.empty:
        return f"无法获取 {symbol} 的数据"

    # 取最近 24h 的微观数据
    df_24h = get_recent_24h(df)
    if len(df_24h) < 20:
        df_24h = df.tail(96)  # fallback

    close = df_24h['close'].iloc[-1]

    # --- VWAP ---
    vwap = calculate_vwap(df_24h)
    vwap_current = vwap.iloc[-1]
    vwap_desc = above_below(close, vwap_current, "价格", "VWAP")
    vwap_trend = trend_direction(vwap)

    # --- MFI ---
    mfi = calculate_mfi(df_24h)
    mfi_current = mfi.dropna().iloc[-1] if not mfi.dropna().empty else 50
    mfi_level = classify_level(mfi_current, {
        '严重超买': 80, '偏多': 60, '中性': 40, '偏空': 20, '严重超卖': 0
    })
    mfi_trend = trend_direction(mfi.dropna())
    mfi_div = divergence_detect(df_24h['close'], mfi.dropna())

    # --- CMF ---
    cmf = calculate_cmf(df_24h)
    cmf_current = cmf.dropna().iloc[-1] if not cmf.dropna().empty else 0
    cmf_flow = "资金净流入 (吸筹)" if cmf_current > 0.05 else \
               "资金净流出 (派发)" if cmf_current < -0.05 else "资金流平衡"
    cmf_trend = trend_direction(cmf.dropna())

    # --- MACD ---
    macd_data = calculate_macd(df_24h)
    macd_cross = cross_detect(macd_data['macd'], macd_data['signal'])
    macd_hist_trend = trend_direction(macd_data['histogram'].dropna())
    macd_zero = "零轴上方 (多头)" if macd_data['macd'].iloc[-1] > 0 else "零轴下方 (空头)"
    macd_roc = rate_of_change(macd_data['histogram'].dropna(), 3)

    sections = [
        ("VWAP", f"{vwap_desc}, VWAP趋势: {vwap_trend}"),
        ("MFI", f"水平: {mfi_level} ({mfi_current:.1f}), "
               f"趋势: {mfi_trend}, 背离: {mfi_div}"),
        ("CMF", f"{cmf_flow} ({cmf_current:.4f}), 趋势: {cmf_trend}"),
        ("MACD", f"交叉: {macd_cross}, 位置: {macd_zero}, "
                f"柱状图动量: {macd_hist_trend}, 变化: {macd_roc}"),
    ]

    report = format_report(f"{symbol} 机构资金流向分析", sections)

    # --- 可选对比 ---
    if optional_symbol:
        df_opt = load_bars(optional_symbol)
        if not df_opt.empty:
            df_opt_24h = get_recent_24h(df_opt)
            if len(df_opt_24h) < 20:
                df_opt_24h = df_opt.tail(96)

            mfi_opt = calculate_mfi(df_opt_24h).dropna()
            cmf_opt = calculate_cmf(df_opt_24h).dropna()
            if not mfi_opt.empty and not cmf_opt.empty:
                report += "\n--- 对比 ---"
                report += f"\n{compare_symbols(mfi_current, mfi_opt.iloc[-1], symbol, optional_symbol, 'MFI')}"
                report += f"\n{compare_symbols(cmf_current, cmf_opt.iloc[-1], symbol, optional_symbol, 'CMF')}"

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Smart Money - 机构资金流向分析")
    parser.add_argument("symbol", help="股票/虚拟货币代码 (如 AAPL, BTC)")
    parser.add_argument("--vs", dest="optional_symbol", default=None,
                        help="对比标的 (如 SPY)")
    args = parser.parse_args()
    print(smart_money(args.symbol, args.optional_symbol))
