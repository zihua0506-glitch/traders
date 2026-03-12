"""
macro_lines.py - 计算宏观指标

指标: MA200, MA50, EMA21, EMA169
核心思想: 宏观均线是市场的"大方向标"。
         MA200 是年度趋势 (牛市/熊市的分界线)，
         MA50 是季度趋势，EMA21/EMA169 是中短期趋势。
         这些线的排列关系决定了整体交易方向。
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools.calculate import (
    load_bars, resample_daily,
    above_below, trend_direction, cross_detect,
    compare_symbols, format_report,
    multi_timeframe_alignment
)


def calculate_ma(data: pd.DataFrame, window: int) -> pd.Series:
    """计算简单移动平均线 (SMA)。"""
    return data['close'].rolling(window=window).mean()


def calculate_ema(data: pd.DataFrame, span: int) -> pd.Series:
    """计算指数移动平均线 (EMA)。"""
    return data['close'].ewm(span=span, adjust=False).mean()


def macro_lines(symbol: str, optional_symbol: str | None = None) -> str:
    """
    主函数: 计算宏观趋势指标并返回相对值分析。

    输入:
        symbol: 主标的代码 (如 'AAPL')
        optional_symbol: 可选对比标的 (如 'SPY')

    输出:
        str: LLM 可读的宏观趋势报告

    LLM 决策指南:
    - 价格 > MA200: 长期牛市，只做多
    - 价格 < MA200: 长期熊市，只做空或观望
    - MA50 上穿 MA200: 黄金交叉 (Golden Cross)，极强看多
    - MA50 下穿 MA200: 死亡交叉 (Death Cross)，极强看空
    - EMA21 > EMA169: 中期多头排列
    - 价格在所有均线之上: 极强多头，但注意乖离率过大
    """
    df = load_bars(symbol)
    if df.empty:
        return f"无法获取 {symbol} 的数据"

    # 从 15min 聚合为日线 (因为 1d interval 数据不准确)
    df_daily = resample_daily(df)

    if len(df_daily) < 50:
        return f"{symbol} 日线数据不足 (需要至少 50 日，当前 {len(df_daily)} 日)"

    close_daily = df_daily['close'].iloc[-1]

    # --- 计算宏观均线 (日线级别) ---
    ma200 = calculate_ma(df_daily, 200)
    ma50 = calculate_ma(df_daily, 50)
    ema21 = calculate_ema(df_daily, 21)
    ema169 = calculate_ema(df_daily, 169)

    sections = []

    # --- MA200 (年度趋势线) ---
    if not ma200.dropna().empty:
        ma200_val = ma200.dropna().iloc[-1]
        ma200_desc = above_below(close_daily, ma200_val, "价格", "MA200")
        ma200_trend = trend_direction(ma200.dropna(), window=10)
        sections.append(("MA200 (年度)", f"{ma200_desc}, 趋势: {ma200_trend}"))
    else:
        sections.append(("MA200 (年度)", "数据不足 (需要200日数据)"))

    # --- MA50 (季度趋势线) ---
    ma50_val = ma50.dropna().iloc[-1] if not ma50.dropna().empty else None
    if ma50_val is not None:
        ma50_desc = above_below(close_daily, ma50_val, "价格", "MA50")
        ma50_trend = trend_direction(ma50.dropna(), window=10)
        sections.append(("MA50 (季度)", f"{ma50_desc}, 趋势: {ma50_trend}"))

    # --- EMA21 (短期动态均线) ---
    ema21_val = ema21.dropna().iloc[-1] if not ema21.dropna().empty else None
    if ema21_val is not None:
        ema21_desc = above_below(close_daily, ema21_val, "价格", "EMA21")
        ema21_trend = trend_direction(ema21.dropna())
        sections.append(("EMA21 (短期)", f"{ema21_desc}, 趋势: {ema21_trend}"))

    # --- EMA169 (中期动态均线) ---
    ema169_val = ema169.dropna().iloc[-1] if not ema169.dropna().empty else None
    if ema169_val is not None:
        ema169_desc = above_below(close_daily, ema169_val, "价格", "EMA169")
        sections.append(("EMA169 (中期)", ema169_desc))

    # --- 均线排列关系 ---
    if ma50_val is not None and not ma200.dropna().empty:
        ma200_val = ma200.dropna().iloc[-1]
        golden_death = cross_detect(ma50.dropna(), ma200.dropna())
        sections.append(("MA50/MA200交叉", golden_death))

    if ema21_val is not None and ema169_val is not None:
        ema_cross = cross_detect(ema21.dropna(), ema169.dropna())
        sections.append(("EMA21/EMA169交叉", ema_cross))

    # --- 均线多空排列综合判断 ---
    vals = {}
    if ema21_val is not None:
        vals['EMA21'] = ema21_val
    if ma50_val is not None:
        vals['MA50'] = ma50_val
    if ema169_val is not None:
        vals['EMA169'] = ema169_val
    if not ma200.dropna().empty:
        vals['MA200'] = ma200.dropna().iloc[-1]

    if len(vals) >= 3:
        sorted_ma = sorted(vals.items(), key=lambda x: x[1], reverse=True)
        order = " > ".join([f"{name}" for name, _ in sorted_ma])
        price_above_all = all(close_daily > v for v in vals.values())
        price_below_all = all(close_daily < v for v in vals.values())

        if price_above_all:
            arrangement = f"极强多头排列 (价格 > {order})"
        elif price_below_all:
            arrangement = f"极强空头排列 (价格 < {order})"
        else:
            arrangement = f"均线排列: {order}"
        sections.append(("排列", arrangement))

    # --- 微观 EMA 与宏观 MA 一致性 ---
    if ema21_val is not None and not ma200.dropna().empty:
        ma200_val = ma200.dropna().iloc[-1]
        micro_sig = "看多" if close_daily > ema21_val else "看空"
        macro_sig = "看多" if close_daily > ma200_val else "看空"
        alignment = multi_timeframe_alignment(micro_sig, macro_sig)
        sections.append(("短长期一致性", alignment))

    report = format_report(f"{symbol} 宏观均线分析", sections)

    # --- 可选对比 ---
    if optional_symbol:
        df_opt = load_bars(optional_symbol)
        if not df_opt.empty:
            df_opt_daily = resample_daily(df_opt)
            if len(df_opt_daily) >= 50:
                opt_close = df_opt_daily['close'].iloc[-1]
                opt_ema21 = calculate_ema(df_opt_daily, 21).iloc[-1]
                opt_ma50 = calculate_ma(df_opt_daily, 50).dropna()
                report += "\n--- 对比 ---"
                if ema21_val is not None:
                    # 比较乖离率 (价格偏离 EMA21 的程度)
                    dev_a = (close_daily - ema21_val) / ema21_val * 100
                    dev_b = (opt_close - opt_ema21) / opt_ema21 * 100 if opt_ema21 != 0 else 0
                    report += f"\n{symbol} EMA21乖离率: {dev_a:+.2f}% vs {optional_symbol}: {dev_b:+.2f}%"

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Macro Lines - 宏观均线分析")
    parser.add_argument("symbol", help="股票/虚拟货币代码 (如 AAPL, BTC)")
    parser.add_argument("--vs", dest="optional_symbol", default=None,
                        help="对比标的 (如 SPY)")
    args = parser.parse_args()
    print(macro_lines(args.symbol, args.optional_symbol))
