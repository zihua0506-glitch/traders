from __future__ import annotations

"""
Alpha Factors Library (alpha.py)
--------------------------------
包含基于统计学、动量加速、市场结构和非线性分析的进阶量化因子。
这些工具用于捕捉 2-4 小时短线交易中的微观市场变化，区别于传统的技术指标。

核心类别:
1. 统计分布类 (Z-Score, Rank, Skewness, Kurtosis)
2. 动量结构类 (Acceleration, Intensity, Efficiency)
3. 复杂性分析类 (Hurst, Entropy)
4. 量价互动类 (Correlation, WQ Alphas)
"""

import os
import sys
import numpy as np
import pandas as pd
from scipy.stats import entropy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools.calculate import (
    load_bars, get_recent_24h,
    classify_level, trend_direction, sigma_position,
    divergence_detect, compare_symbols, format_report
)


def alpha_z_score(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算价格的 Z-Score (标准分)

    逻辑: 均值回归。
    LLM 指南:
    - Z > 2.0: 价格在统计学上显著过高 (超买)，回调风险大。
    - Z < -2.0: 价格在统计学上显著过低 (超卖)，反弹概率大。
    """
    close = df['close']
    mean = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()

    std = std.replace(0, np.nan)
    z_score = (close - mean) / std
    return z_score


def alpha_price_volume_corr(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    计算 价格-成交量 相关性系数 (Price-Volume Correlation)

    逻辑: 量价配合度检测。
    LLM 指南:
    - 值接近 1.0: 量价齐升(健康) 或 量价齐跌(恐慌)。
    - 值接近 -1.0: 量价背离。价格涨但量跌(诱多)，或价格跌但量缩(惜售)。
    """
    return df['close'].rolling(window=window).corr(df['volume'])


def alpha_intraday_intensity(df: pd.DataFrame) -> pd.Series:
    """
    计算 K线实体强度 (Intraday Intensity / Close Location Value)

    公式: (Close - Open) / (High - Low)
    逻辑: 判断单根 K 线内部的多空博弈结果。
    LLM 指南:
    - > 0.8: 光头光脚大阳线，多头完胜。
    - < -0.8: 大阴线，空头完胜。
    - ≈ 0: 十字星 (Doji)，多空平衡，变盘前兆。
    """
    range_hl = (df['high'] - df['low']).replace(0, 0.00001)
    intensity = (df['close'] - df['open']) / range_hl
    return intensity


def alpha_return_acceleration(df: pd.DataFrame, window: int = 3) -> pd.Series:
    """
    计算 收益率加速度 (Return Acceleration)

    逻辑: 价格变化的二阶导数 (动量的动量)。
    LLM 指南:
    - 价格在涨，但加速度 < 0: 上涨动能衰竭，顶部特征。
    - 价格在跌，但加速度 > 0: 下跌减速，底部特征。
    """
    roc = df['close'].pct_change(periods=window)
    acceleration = roc.diff()
    return acceleration


def alpha_ts_rank(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    计算 时间序列排名 (Time Series Rank)

    逻辑: 当前价格在过去 N 个周期中的百分比排名 (0.0 - 1.0)。
    LLM 指南:
    - > 0.95: 处于极高位，类似于 RSI 超买，但基于纯统计分布。
    - < 0.05: 处于极低位。
    """
    def get_rank(array):
        return pd.Series(array).rank(pct=True).iloc[-1]

    return df['close'].rolling(window=window).apply(get_rank, raw=True)


def alpha_wq_006(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    WorldQuant Alpha #006 (简化版)

    公式: -1 * Correlation(Open, Volume, window)
    逻辑: 开盘价与成交量的负相关性。
    LLM 指南:
    - 负值极大: 开盘价越高成交量越大(高开放量)，往往意味着散户追高或机构出货，后市看跌。
    """
    corr = df['open'].rolling(window=window).corr(df['volume'])
    return -1 * corr


def alpha_kurtosis(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算 峰度 (Kurtosis)

    逻辑: 衡量尾部风险 (Fat Tail)。
    LLM 指南:
    - 峰度突然飙升: 市场出现极端跳空或剧烈波动，不再服从正态分布。
    - 此时传统的均值回归策略可能失效，需降低仓位。
    """
    return df['close'].rolling(window=window).kurt()


def alpha_skewness(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算 偏度 (Skewness / Tail Risk)

    逻辑: 衡量收益分布的不对称性。
    LLM 指南:
    - 负偏度 (Negative Skew): "急跌慢涨"。经常出现小涨但偶尔暴跌。
    - 正偏度 (Positive Skew): "急涨慢跌"。经常出现小跌但偶尔暴涨 (彩票型资产)。
    """
    return df['close'].pct_change().rolling(window=window).skew()


def alpha_volume_ratio(df: pd.DataFrame, short_window: int = 5,
                       long_window: int = 20) -> pd.Series:
    """
    计算 量比 (Volume Ratio)

    逻辑: 短期成交量 vs 长期成交量。
    LLM 指南:
    - > 2.0: 显著放量。如果是突破关键位时放量，可信度高。
    - < 0.5: 严重缩量，市场缺乏流动性和方向。
    """
    vol_short = df['volume'].rolling(window=short_window).mean()
    vol_long = df['volume'].rolling(window=long_window).mean()

    vol_long = vol_long.replace(0, np.nan)
    return vol_short / vol_long


def alpha_hurst_exponent(df: pd.DataFrame, window: int = 50) -> pd.Series:
    """
    计算 赫斯特指数 (Hurst Exponent) - 滚动近似版

    逻辑: 区分随机游走(0.5)、均值回归(<0.5)和趋势状态(>0.5)。
    LLM 指南:
    - < 0.45: 均值回归市场。高抛低吸。
    - > 0.55: 趋势市场。追涨杀跌。
    - ≈ 0.50: 随机震荡。观望。
    """
    def get_hurst_simplified(series):
        lags = range(2, 10)
        tau = []
        for lag in lags:
            # series is numpy array (raw=True), compute lag differences manually
            diffs = series[lag:] - series[:-lag]
            tau.append(np.sqrt(np.std(diffs)))
        try:
            tau_arr = np.array(tau)
            # 过滤掉零或负值避免 log 报错
            valid = tau_arr > 0
            if valid.sum() < 2:
                return 0.5
            log_lags = np.log(np.array(list(lags))[valid])
            log_tau = np.log(tau_arr[valid])
            poly = np.polyfit(log_lags, log_tau, 1)
            return poly[0]
        except Exception:
            return 0.5

    hurst = df['close'].rolling(window=window).apply(get_hurst_simplified, raw=True)
    return hurst


def alpha_efficiency_ratio(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    计算 考夫曼效率比 (Kaufman Efficiency Ratio / Fractal Efficiency)

    公式: |Net_Change| / Sum(Absolute_Changes)
    逻辑: 衡量趋势的"纯度"或"顺滑度"。
    LLM 指南:
    - 接近 1.0: 单边趋势极强，噪音少 (Straight line move)。适合加仓。
    - 接近 0.0: 充满噪音的震荡 (Choppy market)。容易被止损，建议离场。
    """
    net_change = df['close'].diff(window).abs()
    path_length = df['close'].diff().abs().rolling(window=window).sum()
    er = net_change / path_length.replace(0, np.nan)
    return er


def alpha_shannon_entropy(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算 价格分布的香农熵 (Shannon Entropy)

    逻辑: 衡量系统混乱程度 (基于信息论)。
    LLM 指南:
    - 熵值降低: 市场正在达成共识，可能即将选择方向 (变盘点)。
    - 熵值极高: 市场混乱，多空分歧巨大。
    """
    def calc_entropy(x):
        counts, _ = np.histogram(x, bins=10, density=True)
        counts = counts[counts > 0]
        return entropy(counts)

    returns = df['close'].pct_change().dropna()
    roll_entropy = returns.rolling(window=window).apply(calc_entropy, raw=True)
    return roll_entropy.reindex(df.index)


def alpha_vwap_deviation(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算 VWAP 偏离度 (VWAP Deviation)

    逻辑: 均值回归因子。
    LLM 指南:
    - 正偏离过大 (> 0.03): 价格远高于平均成本，获利盘可能抛售。
    - 负偏离过大 (< -0.03): 价格远低于平均成本，恐慌盘可能耗尽。
    - 接近 0: 趋势跟随的最佳买点 (回归价值)。
    """
    v = df['volume']
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    vwap_roll = (tp * v).rolling(window=window).sum() / v.rolling(window=window).sum()
    deviation = (df['close'] - vwap_roll) / vwap_roll
    return deviation


def alpha_trend_persistence(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    计算 趋势持续性 (Trend Persistence / Sign Correlation)

    逻辑: 过去 N 根 K 线中，上涨 K 线的占比。
    LLM 指南:
    - > 0.8: 极强多头排列 (80% 的时间在涨)。注意冲高回落。
    - < 0.2: 极强空头排列。
    - 顶背离: 价格创新高，但 Persistence 下降 (上涨变得困难)，预示反转。
    """
    is_up = np.where(df['close'].diff() > 0, 1.0, 0.0)
    is_up_series = pd.Series(is_up, index=df.index)
    persistence = is_up_series.rolling(window=window).mean()
    return persistence


def get_all_alphas(df: pd.DataFrame) -> pd.DataFrame:
    """
    辅助函数: 生成所有 Alpha 因子的汇总 DataFrame
    """
    alphas = pd.DataFrame(index=df.index)

    # 统计分布
    alphas['alpha_z_score'] = alpha_z_score(df)
    alphas['alpha_ts_rank'] = alpha_ts_rank(df)
    alphas['alpha_skew'] = alpha_skewness(df)
    alphas['alpha_kurt'] = alpha_kurtosis(df)

    # 动量与结构
    alphas['alpha_accel'] = alpha_return_acceleration(df)
    alphas['alpha_intensity'] = alpha_intraday_intensity(df)
    alphas['alpha_efficiency'] = alpha_efficiency_ratio(df)
    alphas['alpha_persist'] = alpha_trend_persistence(df)

    # 复杂性与非线性
    alphas['alpha_hurst'] = alpha_hurst_exponent(df)
    alphas['alpha_entropy'] = alpha_shannon_entropy(df)

    # 量价互动
    alphas['alpha_pv_corr'] = alpha_price_volume_corr(df)
    alphas['alpha_wq006'] = alpha_wq_006(df)
    alphas['alpha_vol_ratio'] = alpha_volume_ratio(df)
    alphas['alpha_vwap_dev'] = alpha_vwap_deviation(df)

    return alphas.dropna()


# ==========================================
# 主函数
# ==========================================

def alpha_factors(symbol: str, optional_symbol: str | None = None) -> str:
    """
    主函数: 生成量化 Alpha 因子的综合报告。

    输入:
        symbol: 主标的代码 (如 'AAPL')
        optional_symbol: 可选对比标的 (如 'SPY')

    输出:
        str: LLM 可读的 Alpha 因子分析报告

    包含:
        - 统计分布: Z-Score (均值回归), 时间序列排名, 偏度, 峰度
        - 动量结构: 加速度, K线强度, 效率比, 趋势持续性
        - 复杂性: 赫斯特指数 (趋势/均值回归), 香农熵 (混乱度)
        - 量价: 量价相关性, WQ006, 量比, VWAP偏离
    """
    df = load_bars(symbol)
    if df.empty:
        return f"无法获取 {symbol} 的数据"

    df_24h = get_recent_24h(df)
    if len(df_24h) < 30:
        df_24h = df.tail(96)

    # --- 统计分布类 ---
    z = alpha_z_score(df_24h)
    z_val = z.dropna().iloc[-1] if not z.dropna().empty else 0
    z_desc = sigma_position(z_val, 0, 1)

    ts = alpha_ts_rank(df_24h)
    ts_val = ts.dropna().iloc[-1] if not ts.dropna().empty else 0.5
    ts_level = classify_level(ts_val * 100, {
        '极高位': 95, '高位': 75, '中间': 25, '低位': 5, '极低位': 0
    })

    skew = alpha_skewness(df_24h)
    skew_val = skew.dropna().iloc[-1] if not skew.dropna().empty else 0
    if skew_val < -0.5:
        skew_desc = f"负偏度 ({skew_val:.2f}) → 急跌慢涨型，崩盘风险偏高"
    elif skew_val > 0.5:
        skew_desc = f"正偏度 ({skew_val:.2f}) → 急涨慢跌型，彩票特征"
    else:
        skew_desc = f"偏度接近对称 ({skew_val:.2f})"

    kurt = alpha_kurtosis(df_24h)
    kurt_val = kurt.dropna().iloc[-1] if not kurt.dropna().empty else 0
    if kurt_val > 3:
        kurt_desc = f"肥尾 ({kurt_val:.2f}) → 极端行情频发，传统策略失效风险"
    elif kurt_val > 0:
        kurt_desc = f"轻度肥尾 ({kurt_val:.2f})"
    else:
        kurt_desc = f"薄尾 ({kurt_val:.2f}) → 波动温和"

    # --- 动量结构类 ---
    accel = alpha_return_acceleration(df_24h)
    accel_val = accel.dropna().iloc[-1] if not accel.dropna().empty else 0
    price_dir = "上涨" if df_24h['close'].iloc[-1] > df_24h['close'].iloc[-2] else "下跌"
    if price_dir == "上涨" and accel_val < 0:
        accel_desc = f"加速度 {accel_val:.4f} → 上涨动能衰竭 (顶部特征)"
    elif price_dir == "下跌" and accel_val > 0:
        accel_desc = f"加速度 {accel_val:.4f} → 下跌减速 (底部特征)"
    elif accel_val > 0:
        accel_desc = f"加速度 {accel_val:.4f} → 动能增强"
    else:
        accel_desc = f"加速度 {accel_val:.4f} → 动能减弱"

    intensity = alpha_intraday_intensity(df_24h)
    intensity_val = intensity.iloc[-1]
    if intensity_val > 0.8:
        int_desc = f"K线强度 {intensity_val:.2f} → 大阳线，多头完胜"
    elif intensity_val < -0.8:
        int_desc = f"K线强度 {intensity_val:.2f} → 大阴线，空头完胜"
    elif abs(intensity_val) < 0.1:
        int_desc = f"K线强度 {intensity_val:.2f} → 十字星 (变盘前兆)"
    else:
        int_desc = f"K线强度 {intensity_val:.2f} → {'多头偏强' if intensity_val > 0 else '空头偏强'}"

    er = alpha_efficiency_ratio(df_24h)
    er_val = er.dropna().iloc[-1] if not er.dropna().empty else 0
    if er_val > 0.6:
        er_desc = f"效率比 {er_val:.2f} → 干净趋势，适合加仓"
    elif er_val < 0.3:
        er_desc = f"效率比 {er_val:.2f} → 高噪音震荡，不宜追涨杀跌"
    else:
        er_desc = f"效率比 {er_val:.2f} → 一般"

    persist = alpha_trend_persistence(df_24h)
    persist_val = persist.dropna().iloc[-1] if not persist.dropna().empty else 0.5
    persist_pct = persist_val * 100
    persist_trend = trend_direction(persist.dropna())
    persist_div = divergence_detect(df_24h['close'], persist.dropna())

    # --- 复杂性分析类 ---
    hurst = alpha_hurst_exponent(df_24h)
    hurst_val = hurst.dropna().iloc[-1] if not hurst.dropna().empty else 0.5
    if hurst_val > 0.55:
        hurst_desc = f"Hurst {hurst_val:.2f} → 趋势状态 (追涨杀跌)"
    elif hurst_val < 0.45:
        hurst_desc = f"Hurst {hurst_val:.2f} → 均值回归状态 (高抛低吸)"
    else:
        hurst_desc = f"Hurst {hurst_val:.2f} → 随机震荡 (观望)"

    ent = alpha_shannon_entropy(df_24h)
    ent_val = ent.dropna().iloc[-1] if not ent.dropna().empty else 0
    ent_trend = trend_direction(ent.dropna())
    if "下降" in ent_trend:
        ent_desc = f"熵值 {ent_val:.2f}, 趋势: {ent_trend} → 市场正达成共识，变盘在即"
    elif "上升" in ent_trend:
        ent_desc = f"熵值 {ent_val:.2f}, 趋势: {ent_trend} → 分歧加大，方向不明"
    else:
        ent_desc = f"熵值 {ent_val:.2f}, 趋势: {ent_trend}"

    # --- 量价互动类 ---
    pv = alpha_price_volume_corr(df_24h)
    pv_val = pv.dropna().iloc[-1] if not pv.dropna().empty else 0
    if pv_val > 0.5:
        pv_desc = f"量价相关 {pv_val:.2f} → 量价配合健康"
    elif pv_val < -0.5:
        pv_desc = f"量价相关 {pv_val:.2f} → 量价严重背离"
    else:
        pv_desc = f"量价相关 {pv_val:.2f} → 关系不显著"

    vr = alpha_volume_ratio(df_24h)
    vr_val = vr.dropna().iloc[-1] if not vr.dropna().empty else 1
    if vr_val > 2.0:
        vr_desc = f"量比 {vr_val:.2f} → 显著放量 (突破验证)"
    elif vr_val < 0.5:
        vr_desc = f"量比 {vr_val:.2f} → 严重缩量 (无方向)"
    else:
        vr_desc = f"量比 {vr_val:.2f} → 正常"

    vwap_dev = alpha_vwap_deviation(df_24h)
    vwap_dev_val = vwap_dev.dropna().iloc[-1] if not vwap_dev.dropna().empty else 0
    vwap_dev_pct = vwap_dev_val * 100
    if vwap_dev_val > 0.03:
        vwap_desc = f"VWAP偏离 {vwap_dev_pct:+.2f}% → 超买 (乖离率过大)"
    elif vwap_dev_val < -0.03:
        vwap_desc = f"VWAP偏离 {vwap_dev_pct:+.2f}% → 超卖 (恐慌盘耗尽)"
    else:
        vwap_desc = f"VWAP偏离 {vwap_dev_pct:+.2f}% → 回归价值区间"

    wq = alpha_wq_006(df_24h)
    wq_val = wq.dropna().iloc[-1] if not wq.dropna().empty else 0

    # --- 综合策略建议 ---
    signals = []
    if hurst_val > 0.55:
        signals.append("趋势跟踪")
    elif hurst_val < 0.45:
        signals.append("均值回归")

    if abs(z_val) > 2:
        signals.append(f"Z-Score {'超买' if z_val > 0 else '超卖'}")

    if er_val > 0.6:
        signals.append("趋势纯度高")

    if vr_val > 2.0:
        signals.append("放量突破")

    strategy = ", ".join(signals) if signals else "无明确信号"

    sections = [
        ("Z-Score", f"{z_desc}, 趋势: {trend_direction(z.dropna())}"),
        ("TS-Rank", f"{ts_level} ({ts_val:.2f})"),
        ("偏度", skew_desc),
        ("峰度", kurt_desc),
        ("加速度", accel_desc),
        ("K线强度", int_desc),
        ("效率比", er_desc),
        ("持续性", f"阳线占比 {persist_pct:.0f}%, 趋势: {persist_trend}, 背离: {persist_div}"),
        ("Hurst", hurst_desc),
        ("熵值", ent_desc),
        ("量价", pv_desc),
        ("量比", vr_desc),
        ("VWAP偏离", vwap_desc),
        ("WQ006", f"值 {wq_val:.2f}" + (" → 开盘放量陷阱" if wq_val < -0.5 else "")),
        ("策略建议", strategy),
    ]

    report = format_report(f"{symbol} Alpha因子分析", sections)

    if optional_symbol:
        df_opt = load_bars(optional_symbol)
        if not df_opt.empty:
            df_opt_24h = get_recent_24h(df_opt)
            if len(df_opt_24h) < 30:
                df_opt_24h = df_opt.tail(96)

            z_opt = alpha_z_score(df_opt_24h).dropna()
            er_opt = alpha_efficiency_ratio(df_opt_24h).dropna()
            hurst_opt = alpha_hurst_exponent(df_opt_24h).dropna()
            if not z_opt.empty and not er_opt.empty:
                report += "\n--- 对比 ---"
                report += f"\n{compare_symbols(z_val, z_opt.iloc[-1], symbol, optional_symbol, 'Z-Score')}"
                report += f"\n{compare_symbols(er_val, er_opt.iloc[-1], symbol, optional_symbol, '效率比')}"
                if not hurst_opt.empty:
                    report += f"\n{compare_symbols(hurst_val, hurst_opt.iloc[-1], symbol, optional_symbol, 'Hurst')}"

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Alpha Factors - 量化Alpha因子分析")
    parser.add_argument("symbol", help="股票/虚拟货币代码 (如 AAPL, BTC)")
    parser.add_argument("--vs", dest="optional_symbol", default=None,
                        help="对比标的 (如 SPY)")
    args = parser.parse_args()
    print(alpha_factors(args.symbol, args.optional_symbol))
