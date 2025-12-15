import numpy as np
import pandas as pd

"""
Volatility Tools Library
用于计算股票/加密货币市场不同维度的波动率指标。
适用于 2-4 小时短线预测及风控系统。
"""

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算平均真实波幅 (Average True Range, ATR)
    
    用途: 风控核心指标。用于计算动态止损位 (例如: Price - 2*ATR)。
    
    参数:
    df: 包含 'high', 'low', 'close' 列的 DataFrame
    period: 窗口大小 (默认 14)
    
    返回:
    pd.Series: ATR 值
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 计算三个可能的真实波幅 (True Range) 分量
    # 1. 当前最高 - 当前最低
    tr1 = high - low
    # 2. |当前最高 - 昨日收盘|
    tr2 = (high - close.shift(1)).abs()
    # 3. |当前最低 - 昨日收盘|
    tr3 = (low - close.shift(1)).abs()
    
    # 取三者中的最大值作为当天的 TR
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 使用滚动平均计算 ATR (也可以使用 Wilder's Smoothing，此处为简单移动平均)
    atr = tr.rolling(window=period).mean()
    
    return atr


def calculate_garman_klass_volatility(df: pd.DataFrame, window: int = 20, trading_periods: int = 365*24) -> pd.Series:
    """
    计算 Garman-Klass 波动率
    
    用途: 进阶波动率。比单纯收盘价标准差效率高 8 倍，因为它利用了 OHLC 四个价格信息。
    逻辑: 当 GK 波动率突然放大时，往往意味着 Smart Money (机构) 进场或趋势加速。
    
    参数:
    df: 包含 'open', 'high', 'low', 'close' 列的 DataFrame
    window: 滚动窗口大小 (默认 20)
    trading_periods: 年化参数 (加密货币日内交易通常设为 24*365 或 24*30 视具体时间尺度而定，此处默认小时级数据的年化)
    
    返回:
    pd.Series: 波动率因子
    """
    # 防止除零错误，加一个小常数
    epsilon = 1e-8
    
    log_hl = np.log((df['high'] / df['low']) + epsilon)
    log_co = np.log((df['close'] / df['open']) + epsilon)
    
    # Garman-Klass 公式: 0.5 * ln(H/L)^2 - (2*ln2 - 1) * ln(C/O)^2
    gk_var = 0.5 * log_hl**2 - (2 * np.log(2) - 1) * log_co**2
    
    # 滚动计算均值并开方，得到波动率
    volatility = np.sqrt(gk_var.rolling(window=window).mean())
    
    # 如果需要年化/标准化，可以乘以 sqrt(trading_periods)，否则直接返回原始值作为相对指标
    # volatility = volatility * np.sqrt(trading_periods) 
    
    return volatility


def calculate_parkinson_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算 Parkinson 波动率
    
    用途: 另一种基于极值 (High/Low) 的波动率。
    逻辑: 对日内震荡非常敏感，适合用于判断市场是否处于“混乱”状态。
    
    参数:
    df: 包含 'high', 'low' 列的 DataFrame
    window: 滚动窗口大小
    
    返回:
    pd.Series: 波动率因子
    """
    epsilon = 1e-8
    
    # Parkinson 公式: (1 / (4 * ln(2))) * ln(H/L)^2
    log_hl_sq = np.log((df['high'] / df['low']) + epsilon) ** 2
    const = 1.0 / (4.0 * np.log(2.0))
    
    pk_var = const * log_hl_sq
    
    volatility = np.sqrt(pk_var.rolling(window=window).mean())
    
    return volatility


def calculate_bb_width(df: pd.DataFrame, window: int = 20, num_std: int = 2) -> pd.Series:
    """
    计算布林带带宽 (Bollinger Band Width, BBW)
    
    用途: 捕捉“波动率挤压” (Squeeze)。
    逻辑: 当 BBW 跌至历史低位时，预示着即将在 2-4 小时内发生剧烈变盘 (大涨或大跌)。
    
    参数:
    df: 包含 'close' 列的 DataFrame
    window: 均线窗口 (默认 20)
    num_std: 标准差倍数 (默认 2)
    
    返回:
    pd.Series: 带宽值
    """
    sma = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()
    
    upper_band = sma + (std * num_std)
    lower_band = sma - (std * num_std)
    
    # 防止除零
    sma = sma.replace(0, np.nan)
    
    # 带宽 = (上轨 - 下轨) / 中轨
    bb_width = (upper_band - lower_band) / sma
    
    return bb_width


def calculate_historical_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算历史波动率 (Historical Volatility, HV) - 基于对数收益率
    
    用途: 基础统计指标，用于计算 Z-Score 或作为其他复杂模型的基准。
    
    参数:
    df: 包含 'close' 列的 DataFrame
    window: 滚动窗口
    
    返回:
    pd.Series: 标准差
    """
    # 计算对数收益率: ln(P_t / P_t-1)
    # 使用对数收益率比简单百分比收益率更具时间可加性
    log_returns = np.log(df['close'] / df['close'].shift(1))
    
    # 计算滚动标准差
    volatility = log_returns.rolling(window=window).std()
    
    return volatility


# 简单的测试代码样例
##if __name__ == "__main__":
    # 创建一些模拟数据
    data = {
        'open': [100, 102, 101, 103, 102, 105, 106, 108],
        'high': [103, 104, 103, 105, 104, 108, 110, 112],
        'low':  [99, 101, 100, 102, 101, 104, 105, 107],
        'close': [102, 101, 103, 102, 105, 106, 108, 110]
    }
    df_test = pd.DataFrame(data)
    
    print("--- 模拟数据测试 ---")
    print("ATR (window=3):")
    print(calculate_atr(df_test, period=3).tail(3))
    
    print("\nGK Volatility (window=3):")
    print(calculate_garman_klass_volatility(df_test, window=3).tail(3))
    
    print("\nBB Width (window=3):")
    print(calculate_bb_width(df_test, window=3).tail(3))