import numpy as np
import pandas as pd

"""
Volume Tools Library
用于计算市场资金流向、成交量强度及量价关系指标。
核心作用: 帮助 LLM 识别假突破 (False Breakout) 和 机构吸筹 (Accumulation) 行为。
"""

def calculate_obv(df: pd.DataFrame, slope_window: int = 5) -> pd.DataFrame:
    """
    计算能量潮 (On-Balance Volume, OBV) 及其斜率
    
    用途: 
    1. 识别趋势确认: 价格涨且 OBV 涨 -> 健康趋势。
    2. 识别顶背离: 价格创新高但 OBV 没创新高 -> 诱多 (卖出信号)。
    3. 斜率 (Slope): 用于判断近期资金流入流出的加速度。
    
    参数:
    df: 包含 'close', 'volume' 的 DataFrame
    slope_window: 计算 OBV 斜率的窗口大小 (默认 5)
    
    返回:
    pd.DataFrame: 包含 'obv' 和 'obv_slope' 两列
    """
    # 1. 计算 OBV
    # 如果收盘价上涨，成交量加到 OBV；如果下跌，减去成交量
    change = df['close'].diff()
    direction = np.where(change > 0, 1, -1)
    direction[change == 0] = 0  # 价格不变，OBV 不变
    
    # 累积求和
    obv = (direction * df['volume']).cumsum()
    
    # 2. 计算斜率 (Slope)
    # 使用简单的差分来表示斜率，正值代表资金加速流入
    obv_slope = obv.diff(periods=slope_window)
    
    return pd.DataFrame({
        'obv': obv,
        'obv_slope': obv_slope
    })


def calculate_cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算蔡金资金流量 (Chaikin Money Flow, CMF)
    
    用途: 衡量一段时期内的资金累积/派发情况。
    LLM 逻辑: 
    - CMF > 0.05: 强势买入压力 (Bullish)。
    - CMF < -0.05: 强势卖出压力 (Bearish)。
    - 价格创新低但 CMF 开始回升: 底背离 (潜在反转)。
    
    参数:
    period: 窗口大小 (默认 20)
    """
    high = df['high']
    low = df['low']
    close = df['close']
    volume = df['volume']
    
    # 1. Money Flow Multiplier
    # ((Close - Low) - (High - Close)) / (High - Low)
    # 结果在 -1 到 1 之间。收盘越接近最高价，值越接近 1 (买方强)。
    denominator = high - low
    denominator = denominator.replace(0, np.nan) # 防止除零
    
    mf_multiplier = ((close - low) - (high - close)) / denominator
    
    # 2. Money Flow Volume
    mf_volume = mf_multiplier * volume
    
    # 3. CMF = Sum(MF Volume, n) / Sum(Volume, n)
    cmf = mf_volume.rolling(window=period).sum() / volume.rolling(window=period).sum()
    
    return cmf


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算资金流量指标 (Money Flow Index, MFI)
    
    用途: "带成交量的 RSI"。
    LLM 逻辑:
    - MFI > 80: 严重超买 (比 RSI 更准确，因为有量能确认)。
    - MFI < 20: 严重超卖。
    
    参数:
    period: 窗口大小 (默认 14)
    """
    # 典型价格 (Typical Price)
    tp = (df['high'] + df['low'] + df['close']) / 3
    
    # 原始资金流 (Raw Money Flow)
    rmf = tp * df['volume']
    
    # 区分正向流和负向流
    tp_diff = tp.diff()
    
    positive_flow = np.where(tp_diff > 0, rmf, 0)
    negative_flow = np.where(tp_diff < 0, rmf, 0)
    
    # 转换为 Series 以使用 rolling
    pos_series = pd.Series(positive_flow, index=df.index)
    neg_series = pd.Series(negative_flow, index=df.index)
    
    # 计算周期内的和
    pos_sum = pos_series.rolling(window=period).sum()
    neg_sum = neg_series.rolling(window=period).sum()
    
    # Money Flow Ratio
    # 处理除零情况 (防止负向流为0)
    mfr = pos_sum / neg_series.rolling(window=period).sum().replace(0, 1e-10)
    
    # MFI Formula: 100 - (100 / (1 + MFR))
    mfi = 100 - (100 / (1 + mfr))
    
    return mfi


def calculate_force_index(df: pd.DataFrame, period: int = 13) -> pd.Series:
    """
    计算强力指数 (Force Index)
    
    用途: 确定趋势强度。
    LLM 逻辑:
    - 强力指数极大正值: 上升趋势强劲 (但可能不可持续)。
    - 强力指数极大负值: 下跌恐慌盘。
    - 价格涨但在 0 附近徘徊: 涨势无力 (No conviction)。
    """
    # Force Index = (Current Close - Prior Close) * Current Volume
    fi_raw = df['close'].diff(1) * df['volume']
    
    # 通常使用 EMA 平滑
    force_index = fi_raw.ewm(span=period, adjust=False).mean()
    
    return force_index


def calculate_vwap_rolling(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算滚动成交量加权平均价 (Rolling VWAP)
    *注: 传统 VWAP 是按天重置的，但在 24/7 的加密货币市场，滚动窗口更有意义。
    
    用途: 机构操盘生命线。
    LLM 逻辑:
    - Price > VWAP: 多头控盘 (Bullish Control)。
    - Price < VWAP: 空头控盘 (Bearish Control)。
    - 价格回踩 VWAP 不破: 绝佳买点。
    
    参数:
    window: 滚动窗口 (例如 24 小时线)
    """
    v = df['volume']
    tp = (df['high'] + df['low'] + df['close']) / 3
    
    # 滚动计算 (TP * V).sum() / V.sum()
    vwap = (tp * v).rolling(window=window).sum() / v.rolling(window=window).sum()
    
    return vwap


def calculate_volume_z_score(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算成交量 Z-Score (异常值检测)
    
    用途: 告诉 LLM 当前成交量是否“异常巨大”。
    LLM 逻辑:
    - Z-Score > 3.0: 巨量 (Spike)。通常对应底部吸筹或顶部出货。
    """
    vol = df['volume']
    mean_vol = vol.rolling(window=window).mean()
    std_vol = vol.rolling(window=window).std()
    
    z_score = (vol - mean_vol) / std_std
    
    return z_score


# 简单的测试代码
##if __name__ == "__main__":
    # 创建模拟数据
    data = {
        'high':  [10, 12, 11, 13, 12, 15, 16],
        'low':   [8,  9,  9,  11, 10, 13, 14],
        'close': [9,  11, 10, 12, 11, 14, 15],
        'volume': [100, 150, 80, 200, 120, 300, 250]
    }
    df_test = pd.DataFrame(data)
    
    print("--- Volume Tools Test ---")
    print("OBV Slope (window=2):")
    print(calculate_obv(df_test, slope_window=2)['obv_slope'].tail(3))
    
    print("\nCMF (window=3):")
    print(calculate_cmf(df_test, period=3).tail(3))
    
    print("\nMFI (window=3):")
    print(calculate_mfi(df_test, period=3).tail(3))