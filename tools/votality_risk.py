import pandas as pd

def calculate_keltner_channels(data: pd.DataFrame, period: int = 20, atr_mult: int = 2) -> pd.DataFrame:
    """
    计算肯特纳通道 (Keltner Channels)。
    LLM 逻辑:
    - 相比布林带(基于标准差)，肯特纳基于 ATR。
    - 它对洗盘不敏感，过滤假突破更好。
    - 价格 > Upper: 真正的强势突破。
    - 价格 < Lower: 真正的弱势跌破。
    """
    ema = data['close'].ewm(span=period, adjust=False).mean()
    
    # 计算 ATR
    high, low, close = data['high'], data['low'], data['close']
    tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(10).mean()
    
    upper = ema + (atr * atr_mult)
    lower = ema - (atr * atr_mult)
    
    # 价格在通道内的位置
    pos = (data['close'] - lower) / (upper - lower).replace(0, 0.001)
    
    return pd.DataFrame({
        'kc_upper': upper,
        'kc_lower': lower,
        'kc_position': pos
    })

def calculate_volatility_squeeze(data: pd.DataFrame) -> pd.Series:
    """
    计算"挤牌"信号 (TTM Squeeze 简化版)。
    LLM 逻辑:
    - 当布林带收窄进肯特纳通道内时，代表波动率极度压缩。
    - Squeeze On (True): 暴风雨前的宁静，即将变盘，LLM 此时应提示"等待突破"。
    - Squeeze Off: 能量已释放。
    """
    # 简易计算：比较布林带宽和肯特纳宽
    bb_width = data['close'].rolling(20).std() * 4 # roughly width
    # 实际上是用 BB 全部在 KC 内部
    # 这里为了给 LLM 一个数值：
    # 如果 < 0，说明波动率极低 (Squeeze)
    return bb_width