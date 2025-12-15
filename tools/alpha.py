import numpy as np
import pandas as pd
from scipy.stats import entropy, linregress

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
    
    # 防止除零
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
    range_hl = (df['high'] - df['low']).replace(0, 0.00001) # 防止除零
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
    # 1. 计算一阶动量 (ROC)
    roc = df['close'].pct_change(periods=window)
    # 2. 计算二阶动量 (ROC 的变化率)
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


def alpha_volume_ratio(df: pd.DataFrame, short_window: int = 5, long_window: int = 20) -> pd.Series:
    """
    计算 量比 (Volume Ratio)
    
    逻辑: 短期成交量 vs 长期成交量。
    LLM 指南:
    - > 2.0: 显著放量。如果是突破关键位时放量，可信度高。
    - < 0.5: 严重缩量，市场缺乏流动性和方向。
    """
    vol_short = df['volume'].rolling(window=short_window).mean()
    vol_long = df['volume'].rolling(window=long_window).mean()
    
    # 防止除零
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
    # 这是一个简化的高效计算版本，利用波动率随时间尺度的缩放特性
    def get_hurst_simplified(series):
        lags = range(2, 10)
        # 计算滞后差分的标准差
        tau = [np.sqrt(np.std(series.diff(lag))) for lag in lags]
        # 回归 log(tau) vs log(lags)
        # H = slope
        try:
            poly = np.polyfit(np.log(lags), np.log(tau), 1)
            return poly[0]
        except:
            return 0.5

    # 注意：计算量较大，生产环境建议优化步长或减少窗口
    hurst = df['close'].rolling(window=window).apply(get_hurst_simplified, raw=True)
    return hurst


def alpha_efficiency_ratio(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    计算 考夫曼效率比 (Kaufman Efficiency Ratio / Fractal Efficiency)
    
    公式: |Net_Change| / Sum(Absolute_Changes)
    逻辑: 衡量趋势的“纯度”或“顺滑度”。
    LLM 指南:
    - 接近 1.0: 单边趋势极强，噪音少 (Straight line move)。适合加仓。
    - 接近 0.0: 充满噪音的震荡 (Choppy market)。容易被止损，建议离场。
    """
    # 周期内的净位移
    net_change = df['close'].diff(window).abs()
    
    # 周期内每一步波动的总和 (路径长度)
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
        # 将数据离散化为直方图 (10个桶)
        counts, _ = np.histogram(x, bins=10, density=True)
        # 过滤掉 0 以防 log(0)
        counts = counts[counts > 0]
        return entropy(counts)

    # 基于收益率计算
    returns = df['close'].pct_change().dropna()
    # 使用 rolling apply
    roll_entropy = returns.rolling(window=window).apply(calc_entropy, raw=True)
    
    # 对齐索引
    return roll_entropy.reindex(df.index)


def alpha_vwap_deviation(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算 VWAP 偏离度 (VWAP Deviation)
    
    逻辑: 均值回归因子。
    注意: 这里内部计算简单的滚动 VWAP 仅用于计算偏离度因子，不输出 VWAP 线本身。
    LLM 指南:
    - 正偏离过大 (> 0.03): 价格远高于平均成本，获利盘可能抛售。
    - 负偏离过大 (< -0.03): 价格远低于平均成本，恐慌盘可能耗尽。
    - 接近 0: 趋势跟随的最佳买点 (回归价值)。
    """
    v = df['volume']
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    
    # 计算滚动 VWAP
    vwap_roll = (tp * v).rolling(window=window).sum() / v.rolling(window=window).sum()
    
    # 计算偏离度百分比
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
    # 1 为涨，0 为跌 (平盘算0)
    is_up = np.where(df['close'].diff() > 0, 1.0, 0.0)
    is_up_series = pd.Series(is_up, index=df.index)
    
    persistence = is_up_series.rolling(window=window).mean()
    return persistence


def get_all_alphas(df: pd.DataFrame) -> pd.DataFrame:
    """
    辅助函数: 生成所有 Alpha 因子的汇总报表
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


# --- 测试代码 ---
##if __name__ == "__main__":
    # 生成模拟数据
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=200, freq='15min')
    
    # 模拟一个带趋势和震荡的价格序列
    returns = np.random.normal(0, 0.01, 200)
    price = 100 * np.exp(np.cumsum(returns))
    
    data = {
        'open': price * (1 + np.random.normal(0, 0.002, 200)),
        'close': price,
        'high': price * (1 + np.abs(np.random.normal(0, 0.005, 200))),
        'low': price * (1 - np.abs(np.random.normal(0, 0.005, 200))),
        'volume': np.random.randint(100, 1000, 200) * (1 + np.abs(returns)*10) # 波动大时量大
    }
    
    df_test = pd.DataFrame(data, index=dates)
    
    # 修正 high/low 逻辑错误 (防止随机数导致 low > high)
    df_test['high'] = df_test[['open', 'close', 'high']].max(axis=1)
    df_test['low'] = df_test[['open', 'close', 'low']].min(axis=1)

    print("--- Alpha Factors Calculation Test ---")
    report = get_all_alphas(df_test)
    
    print(f"生成的因子数量: {report.shape[1]}")
    print("\n最新 3 行因子数据:")
    print(report.tail(3).T) # 转置打印以便查看