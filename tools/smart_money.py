import pandas as pd
import numpy as np

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
    # 注意：这里计算的是整个传入窗口的 VWAP。
    # 如果是日内，传入数据应仅包含当日数据。
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
    
    # 逐行遍历比较 (为了准确性)
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
    # Money Flow Multiplier
    mfm = ((data['close'] - data['low']) - (data['high'] - data['close'])) / (data['high'] - data['low']).replace(0, 0.001)
    mfv = mfm * data['volume']
    
    cmf = mfv.rolling(period).sum() / data['volume'].rolling(period).sum()
    return cmf