import pandas as pd
import numpy as np

def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算相对强弱指数 (RSI)。
    LLM 逻辑:
    - RSI > 70: 超买 (可能回调)。
    - RSI < 30: 超卖 (可能反弹)。
    - RSI > 50: 多头趋势; RSI < 50: 空头趋势。
    """
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)

    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_stoch_rsi(data: pd.DataFrame, period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> pd.DataFrame:
    """
    计算随机 RSI (StochRSI)。
    LLM 逻辑:
    - 比普通 RSI 更敏感，适合短线(2-4h)。
    - StochRSI > 0.8: 极度超买 (强烈卖出信号)。
    - StochRSI < 0.2: 极度超卖 (强烈买入信号)。
    - K线穿过D线: 金叉/死叉信号。
    """
    rsi = calculate_rsi(data, period)
    stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min())
    
    # 平滑处理得到 K 和 D 线
    k = stoch_rsi.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    
    return pd.DataFrame({'stoch_rsi_k': k, 'stoch_rsi_d': d})

def calculate_macd(data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    计算 MACD (异同移动平均线)。
    LLM 逻辑:
    - macd_hist > 0 且在变大: 动能增强 (涨)。
    - macd_line 上穿 signal_line: 金叉 (买入)。
    - macd_line 下穿 signal_line: 死叉 (卖出)。
    """
    exp1 = data['close'].ewm(span=fast, adjust=False).mean()
    exp2 = data['close'].ewm(span=slow, adjust=False).mean()
    
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    return pd.DataFrame({
        'macd_line': macd_line,
        'macd_signal': signal_line,
        'macd_hist': macd_hist
    })

def calculate_adx(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    计算平均趋向指标 (ADX) - 趋势强度过滤器。
    LLM 逻辑:
    - ADX < 20: 无趋势/震荡 (建议观望或用震荡策略)。
    - ADX > 25: 趋势形成。
    - ADX > 50: 极强趋势。
    - Plus_DI > Minus_DI: 上涨趋势。
    """
    high = data['high']
    low = data['low']
    close = data['close']
    
    # 1. 计算 True Range (TR)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 2. 计算方向移动 (DM)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    # 3. 平滑处理
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / atr)
    
    # 4. 计算 DX 和 ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return pd.DataFrame({
        'adx': adx,
        'plus_di': plus_di,
        'minus_di': minus_di
    })

def calculate_cci(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算商品通道指标 (CCI)。
    LLM 逻辑:
    - 专门捕捉极端价格波动。
    - CCI > 100: 强势突破 (但也可能即将回调)。
    - CCI < -100: 弱势下跌。
    - 0轴: 多空分界线。
    """
    tp = (data['high'] + data['low'] + data['close']) / 3
    sma_tp = tp.rolling(period).mean()
    mad_tp = tp.rolling(period).apply(lambda x: pd.Series(x).mad()) # Mean Absolute Deviation
    
    cci = (tp - sma_tp) / (0.015 * mad_tp)
    return cci

def calculate_ma_slope(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算移动平均线的斜率 (MA Slope)。
    这是一个进阶指标，直接告诉 LLM 趋势的角度。
    LLM 逻辑:
    - 正值: 上升趋势; 负值: 下降趋势。
    - 绝对值越大，趋势越陡峭/强烈。
    - 接近 0: 横盘整理。
    """
    ma = data['close'].rolling(period).mean()
    # 计算斜率：(当前MA - N天前MA) / N
    slope = np.arctan((ma - ma.shift(5)) / 5) * (180 / np.pi) # 转换为角度
    return slope

# --- 封装函数，供 LLM 直接调用 ---

def get_momentum_trend_report(price_data_json: str) -> dict:
    """
    工具函数：输入 JSON 格式的价格数据，返回所有动量和趋势指标的最新值。
    Args:
        price_data_json: 包含 high, low, close, volume 的 JSON 字符串
    """
    try:
        # 假设输入是 JSON 列表
        df = pd.read_json(price_data_json)
        
        # 确保列名小写
        df.columns = [c.lower() for c in df.columns]
        
        # 计算所有指标
        results = {}
        
        # 1. RSI
        results['rsi_14'] = calculate_rsi(df).iloc[-1]
        
        # 2. Stoch RSI
        stoch = calculate_stoch_rsi(df)
        results['stoch_k'] = stoch['stoch_rsi_k'].iloc[-1]
        results['stoch_d'] = stoch['stoch_rsi_d'].iloc[-1]
        
        # 3. MACD
        macd = calculate_macd(df)
        results['macd_hist'] = macd['macd_hist'].iloc[-1]
        # 判断金叉/死叉状态
        results['macd_cross_signal'] = "BULLISH" if macd['macd_line'].iloc[-1] > macd['macd_signal'].iloc[-1] else "BEARISH"
        
        # 4. ADX
        adx_data = calculate_adx(df)
        results['adx_strength'] = adx_data['adx'].iloc[-1]
        results['trend_direction'] = "UP" if adx_data['plus_di'].iloc[-1] > adx_data['minus_di'].iloc[-1] else "DOWN"
        
        # 5. CCI
        results['cci_20'] = calculate_cci(df).iloc[-1]
        
        # 6. MA Slope
        results['ma20_slope_angle'] = calculate_ma_slope(df).iloc[-1]
        
        return results
        
    except Exception as e:
        return {"error": str(e)}