"""
function_list.py

所有可供 Agent 使用的量化分析工具的综合定义列表。
分组类别: 波动率 (Volatility), 成交量 (Volume), 量化因子 (Alpha), 以及 动量 (Momentum)。
"""

import pandas as pd
import numpy as np

# ==========================================
# 1. 波动率工具 (Volatility Tools) - 风险与范围
# ==========================================

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算平均真实波幅 (Average True Range, ATR)。

    输入:
        df: 包含 'high', 'low', 'close' 的 DataFrame。
        period: 窗口大小 (默认 14)。

    输出:
        pd.Series: 绝对价格波动的数值。

    执行逻辑与解读:
        1. 使用真实波幅 (True Range) 公式捕捉跳空缺口和极值移动。
        2. LLM 决策行动 (LLM Action):
           - 止损设置 (STOP LOSS): 建议设置在 '当前价格 +/- 2 * ATR'。
           - 趋势过滤 (FILTER): 如果 ATR 正在扩大，说明趋势强劲；如果 ATR 缩小，说明市场正在盘整。
    """
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calculate_garman_klass_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算 Garman-Klass 波动率 (高效率估算器)。

    输入:
        df: 包含 'open', 'high', 'low', 'close' 的 DataFrame。
        window: 窗口大小。

    输出:
        pd.Series: 波动率因子。

    执行逻辑与解读:
        1. 利用 OHLC 四个价格数据，比单纯使用收盘价的标准差能更捕捉日内震荡，效率高 8 倍。
        2. LLM 决策行动 (LLM Action):
           - 警报 (ALERT): 如果数值 > 2倍均值，预示即将发生重大突破或崩盘 (通常是聪明钱/Smart Money 进场)。
           - 注意 (CAUTION): 高 GK 波动率意味着市场处于混乱状态。
    """
    log_hl = np.log(df['high'] / df['low']) ** 2
    log_co = np.log(df['close'] / df['open']) ** 2
    gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
    return gk.rolling(window=window).mean()


def calculate_parkinson_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算 Parkinson 波动率 (基于最高/最低价范围)。

    输入:
        df: 包含 'high', 'low' 的 DataFrame。

    输出:
        pd.Series: 波动率因子。

    执行逻辑与解读:
        1. 专注于 High-Low 范围的扩展。
        2. LLM 决策行动 (LLM Action): 用于评估 K 线内部的"混乱/震荡程度" (Choppiness)。
    """
    log_hl_sq = np.log(df['high'] / df['low']) ** 2
    factor = 1.0 / (4.0 * np.log(2))
    return np.sqrt(factor * log_hl_sq.rolling(window=window).mean())


def calculate_bb_width(df: pd.DataFrame, window: int = 20, num_std: int = 2) -> pd.Series:
    """
    计算布林带带宽 (Bollinger Band Width, BBW)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 带宽比率。

    执行逻辑与解读:
        1. 衡量布林带的"挤压"程度 (Squeeze)。
        2. LLM 决策行动 (LLM Action):
           - 挤压警报 (SQUEEZE ALERT): 如果 BBW 跌至数周低点，预示着 2-4 小时内将发生剧烈变盘 (方向未定，但波动极大)。
    """
    sma = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return (upper - lower) / sma


def calculate_historical_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算标准历史波动率 (基于对数收益率)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 对数收益率的标准差。

    执行逻辑与解读:
        1. 基础统计指标。
        2. LLM 决策行动 (LLM Action): 用作计算夏普比率 (Sharpe Ratio) 的分母，作为基准参考。
    """
    log_returns = np.log(df['close'] / df['close'].shift(1))
    return log_returns.rolling(window=window).std()


# ==========================================
# 2. 成交量工具 (Volume Tools) - 资金流与强度
# ==========================================

def calculate_obv(df: pd.DataFrame, slope_window: int = 5) -> pd.DataFrame:
    """
    计算能量潮 (OBV) 及其斜率 (Slope)。

    输入:
        df: 包含 'close', 'volume' 的 DataFrame。
        slope_window: 计算斜率的窗口。

    输出:
        pd.DataFrame: 包含 'obv' (累积值) 和 'obv_slope' (动量值) 两列。

    执行逻辑与解读:
        1. 基于价格涨跌方向的累积成交量流向。
        2. LLM 决策行动 (LLM Action):
           - 确认 (CONFIRMATION): 价格上涨 + OBV 上涨 = 安全买入。
           - 背离 (DIVERGENCE): 价格上涨 + OBV 下跌/走平 = 诱多陷阱 (建议卖出)。
    """
    direction = np.where(df['close'] > df['close'].shift(1), 1,
                np.where(df['close'] < df['close'].shift(1), -1, 0))
    obv = (df['volume'] * direction).cumsum()
    obv_slope = obv.diff(slope_window)
    return pd.DataFrame({'obv': obv, 'obv_slope': obv_slope})


def calculate_cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算蔡金资金流量 (Chaikin Money Flow, CMF)。

    输入:
        df: 包含 'high', 'low', 'close', 'volume' 的 DataFrame。

    输出:
        pd.Series: 震荡指标 (-1 到 1)。

    执行逻辑与解读:
        1. 衡量一段时间内的吸筹 (Accumulation) 或派发 (Distribution) 压力。
        2. LLM 决策行动 (LLM Action):
           - 买入信号 (BUY): CMF > 0.05 (资金净流入)。
           - 卖出信号 (SELL): CMF < -0.05 (资金净流出)。
    """
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / \
          (df['high'] - df['low']).replace(0, 0.001)
    mfv = mfm * df['volume']
    return mfv.rolling(period).sum() / df['volume'].rolling(period).sum()


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算资金流量指标 (Money Flow Index, MFI)。

    输入:
        df: 包含 OHLCV 数据的 DataFrame。

    输出:
        pd.Series: 0-100 的震荡指标。

    执行逻辑与解读:
        1. 带成交量权重的 RSI。
        2. LLM 决策行动 (LLM Action):
           - > 80: 强力超买 (比普通 RSI 信号更强)。
           - < 20: 强力超卖。
    """
    tp = (df['high'] + df['low'] + df['close']) / 3
    raw_money_flow = tp * df['volume']

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

    pos_mf = pd.Series(positive_flow, index=df.index).rolling(period).sum()
    neg_mf = pd.Series(negative_flow, index=df.index).rolling(period).sum()
    return 100 - (100 / (1 + pos_mf / neg_mf.replace(0, 0.001)))


def calculate_force_index(df: pd.DataFrame, period: int = 13) -> pd.Series:
    """
    计算强力指数 (Force Index)。

    输入:
        df: 包含 'close', 'volume' 的 DataFrame。

    输出:
        pd.Series: 强力值。

    执行逻辑与解读:
        1. 公式: (当前收盘 - 昨日收盘) * 成交量。
        2. LLM 决策行动 (LLM Action): 巨大的柱状图尖峰代表市场信念 (Conviction)。在 0 附近徘徊代表噪音。
    """
    raw_force = df['close'].diff() * df['volume']
    return raw_force.ewm(span=period, adjust=False).mean()


def calculate_vwap_rolling(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算滚动 VWAP (成交量加权平均价)。

    输入:
        df: 包含 OHLCV 数据的 DataFrame。
        window: 滚动周期 (例如 24 代表 24小时)。

    输出:
        pd.Series: 价格水平。

    执行逻辑与解读:
        1. 机构的平均持仓成本线 (Institutional benchmark)。
        2. LLM 决策行动 (LLM Action):
           - 看多 (BULLISH): 价格站稳在 VWAP 之上。
           - 看空 (BEARISH): 价格无法收复 VWAP。
    """
    tp = (df['high'] + df['low'] + df['close']) / 3
    tp_vol = tp * df['volume']
    return tp_vol.rolling(window=window).sum() / df['volume'].rolling(window=window).sum()


def calculate_volume_z_score(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算成交量 Z-Score (标准分)。

    输入:
        df: 包含 'volume' 的 DataFrame。

    输出:
        pd.Series: 距离平均成交量的标准差倍数。

    执行逻辑与解读:
        1. 检测相对成交量的异常峰值。
        2. LLM 决策行动 (LLM Action): 如果 Z > 3.0，代表发生重大流动性事件 (恐慌投降或高潮抢购)。
    """
    vol_mean = df['volume'].rolling(window=window).mean()
    vol_std = df['volume'].rolling(window=window).std()
    return (df['volume'] - vol_mean) / vol_std.replace(0, 0.001)


# ==========================================
# 3. Alpha 因子工具 (Alpha Tools) - 量化与结构
# ==========================================

def alpha_z_score(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算价格 Z-Score (均值回归因子)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: Sigma 数值。

    执行逻辑与解读:
        1. 统计学上偏离均值的程度。
        2. LLM 决策行动 (LLM Action):
           - > 2.0: 统计学上的昂贵 (超买 -> 做空/减仓)。
           - < -2.0: 统计学上的便宜 (超卖 -> 做多/补仓)。
    """
    close = df['close']
    mean = close.rolling(window=window).mean()
    std = close.rolling(window=window).std().replace(0, np.nan)
    return (close - mean) / std


def alpha_price_volume_corr(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    计算 量-价 相关性 (Price-Volume Correlation)。

    输入:
        df: 包含 'close', 'volume' 的 DataFrame。

    输出:
        pd.Series: 相关系数 (-1 到 1)。

    执行逻辑与解读:
        1. 衡量成交量是否支持价格走势。
        2. LLM 决策行动 (LLM Action): 负值意味着背离 (例如价涨量缩)，暗示趋势疲软。
    """
    return df['close'].rolling(window=window).corr(df['volume'])


def alpha_intraday_intensity(df: pd.DataFrame) -> pd.Series:
    """
    计算日内强度 (Intraday Intensity / Close Location Value)。

    输入:
        df: 包含 'open', 'high', 'low', 'close' 的 DataFrame。

    输出:
        pd.Series: -1 到 1 的数值。

    执行逻辑与解读:
        1. 公式: (Close - Open) / (High - Low)。
        2. LLM 决策行动 (LLM Action): 接近 1.0 意味着多头完全控制了这根 K 线 (光头阳线)。
    """
    range_hl = (df['high'] - df['low']).replace(0, 0.00001)
    return (df['close'] - df['open']) / range_hl


def alpha_return_acceleration(df: pd.DataFrame, window: int = 3) -> pd.Series:
    """
    计算收益率加速度 (二阶导数)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 加速度值。

    执行逻辑与解读:
        1. 变化率的变化率 (动量的动量)。
        2. LLM 决策行动 (LLM Action): 在下跌趋势中出现正加速度，预示着下跌减速，底部可能临近。
    """
    roc = df['close'].pct_change(periods=window)
    return roc.diff()


def alpha_ts_rank(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    计算时间序列排名 (Time Series Rank)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 百分比排名 (0 到 1)。

    执行逻辑与解读:
        1. 当前价格在过去 N 个周期中的相对位置。
        2. LLM 决策行动 (LLM Action): > 0.95 处于极度高位 (超买风险)。
    """
    def get_rank(array):
        return pd.Series(array).rank(pct=True).iloc[-1]
    return df['close'].rolling(window=window).apply(get_rank, raw=True)


def alpha_wq_006(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    计算 WorldQuant Alpha #006。

    输入:
        df: 包含 'open', 'volume' 的 DataFrame。

    输出:
        pd.Series: Alpha 因子值。

    执行逻辑与解读:
        1. 公式: -1 * Correlation(Open, Volume)。
        2. LLM 决策行动 (LLM Action): 极度负值暗示"开盘放量"是陷阱，预示趋势反转。
    """
    return -1 * df['open'].rolling(window=window).corr(df['volume'])


def alpha_kurtosis(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算峰度 (Kurtosis - 肥尾风险)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 峰度值。

    执行逻辑与解读:
        1. 衡量极端结果发生的频率。
        2. LLM 决策行动 (LLM Action): 突然飙升意味着市场脱离了正态分布 (高风险)，建议降低仓位。
    """
    return df['close'].rolling(window=window).kurt()


def alpha_skewness(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算偏度 (Skewness - 不对称性)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 偏度值。

    执行逻辑与解读:
        1. 衡量收益分布的不对称性。
        2. LLM 决策行动 (LLM Action): 负偏度意味着"崩盘风险" (慢涨急跌)。
    """
    return df['close'].pct_change().rolling(window=window).skew()


def alpha_volume_ratio(df: pd.DataFrame, short_window: int = 5,
                       long_window: int = 20) -> pd.Series:
    """
    计算量比 (Volume Ratio - 短期 vs 长期)。

    输入:
        df: 包含 'volume' 的 DataFrame。

    输出:
        pd.Series: 比率。

    执行逻辑与解读:
        1. 衡量相对成交量强度。
        2. LLM 决策行动 (LLM Action): > 2.0 验证了突破的有效性 (真突破)。
    """
    vol_short = df['volume'].rolling(window=short_window).mean()
    vol_long = df['volume'].rolling(window=long_window).mean()
    return vol_short / vol_long.replace(0, np.nan)


def alpha_hurst_exponent(df: pd.DataFrame, window: int = 50) -> pd.Series:
    """
    计算赫斯特指数 (Hurst Exponent - 市场状态)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 0-1 的数值。

    执行逻辑与解读:
        1. 区分市场是"趋势状态"还是"均值回归状态"。
        2. LLM 决策行动 (LLM Action):
           - > 0.55: 趋势中 (Trending)。策略：使用均线、追涨杀跌。
           - < 0.45: 均值回归中 (Mean Reverting)。策略：使用震荡指标、网格交易。
    """
    def get_hurst(series):
        lags = range(2, 10)
        tau = [np.sqrt(np.std(series.diff(lag))) for lag in lags]
        try:
            poly = np.polyfit(np.log(lags), np.log(tau), 1)
            return poly[0]
        except Exception:
            return 0.5

    return df['close'].rolling(window=window).apply(get_hurst, raw=True)


def alpha_efficiency_ratio(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    计算考夫曼效率比 (Kaufman Efficiency Ratio - 趋势纯度)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 0-1 的数值。

    执行逻辑与解读:
        1. 净位移 / 总路径长度。
        2. LLM 决策行动 (LLM Action): 高数值 (> 0.6) 表示"干净、流畅"的趋势，适合高杠杆入场。
    """
    net_change = df['close'].diff(window).abs()
    path_length = df['close'].diff().abs().rolling(window=window).sum()
    return net_change / path_length.replace(0, np.nan)


def alpha_shannon_entropy(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算香农熵 (Shannon Entropy - 市场混乱度)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 熵值。

    执行逻辑与解读:
        1. 衡量价格收益的无序程度。
        2. LLM 决策行动 (LLM Action): 熵值下降意味着市场正在达成共识，变盘在即。
    """
    from scipy.stats import entropy

    def calc_entropy(x):
        counts, _ = np.histogram(x, bins=10, density=True)
        counts = counts[counts > 0]
        return entropy(counts)

    returns = df['close'].pct_change().dropna()
    roll_entropy = returns.rolling(window=window).apply(calc_entropy, raw=True)
    return roll_entropy.reindex(df.index)


def alpha_vwap_deviation(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    计算 VWAP 偏离度 (VWAP Deviation % - 估值)。

    输入:
        df: 包含 OHLCV 数据的 DataFrame。

    输出:
        pd.Series: 百分比偏离。

    执行逻辑与解读:
        1. 价格距离 VWAP 的远近。
        2. LLM 决策行动 (LLM Action): > 0.03 (3%) 通常是日内超买信号 (乖离率过大)，可能回调。
    """
    v = df['volume']
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    vwap_roll = (tp * v).rolling(window=window).sum() / v.rolling(window=window).sum()
    return (df['close'] - vwap_roll) / vwap_roll


def alpha_trend_persistence(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    计算趋势持续性 (Trend Persistence)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 0-1 (阳线出现的概率)。

    执行逻辑与解读:
        1. 窗口内上涨 K 线的占比。
        2. LLM 决策行动 (LLM Action): 如果价格创新高，但持续性数值下降，预示顶背离反转。
    """
    is_up = np.where(df['close'].diff() > 0, 1.0, 0.0)
    is_up_series = pd.Series(is_up, index=df.index)
    return is_up_series.rolling(window=window).mean()


# ==========================================
# 4. 动量工具 (Momentum Tools) - 速度与反转
# ==========================================

def calculate_stoch_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    计算随机 RSI (Stochastic RSI)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.DataFrame: 包含 'stoch_rsi_k', 'stoch_rsi_d'。

    执行逻辑与解读:
        1. 将 Stochastic 公式应用于 RSI 值，极其灵敏。
        2. LLM 决策行动 (LLM Action):
           - 金叉 (GOLDEN CROSS): 在超卖区 (< 0.2) K线上穿D线，是首选买入信号。
    """
    # 先算 RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, 0.001)
    rsi = 100 - (100 / (1 + rs))

    # 再对 RSI 做 Stochastic
    rsi_min = rsi.rolling(window=period).min()
    rsi_max = rsi.rolling(window=period).max()
    stoch_rsi_k = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, 0.001)
    stoch_rsi_d = stoch_rsi_k.rolling(window=3).mean()

    return pd.DataFrame({'stoch_rsi_k': stoch_rsi_k, 'stoch_rsi_d': stoch_rsi_d})


def calculate_tsi(df: pd.DataFrame, long_window: int = 25,
                  short_window: int = 13) -> pd.Series:
    """
    计算真实强弱指数 (True Strength Index, TSI)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: TSI 数值。

    执行逻辑与解读:
        1. 双重平滑动量指标，滞后极低。
        2. LLM 决策行动 (LLM Action): 方向性偏见。如果 > 0，只寻找做多机会；反之做空。
    """
    momentum = df['close'].diff()
    # 双重 EMA 平滑
    smooth1 = momentum.ewm(span=long_window, adjust=False).mean()
    double_smooth = smooth1.ewm(span=short_window, adjust=False).mean()

    abs_smooth1 = momentum.abs().ewm(span=long_window, adjust=False).mean()
    abs_double_smooth = abs_smooth1.ewm(span=short_window, adjust=False).mean()

    return 100 * double_smooth / abs_double_smooth.replace(0, 0.001)


def calculate_awesome_oscillator(df: pd.DataFrame) -> pd.Series:
    """
    计算动量震荡指标 (Awesome Oscillator, AO)。

    输入:
        df: 包含 'high', 'low' 的 DataFrame。

    输出:
        pd.Series: AO 数值。

    执行逻辑与解读:
        1. 5周期与34周期中点均线的差值。
        2. LLM 决策行动 (LLM Action): 关注"零轴穿越"和"颜色翻转"作为入场时机。
    """
    midpoint = (df['high'] + df['low']) / 2
    return midpoint.rolling(window=5).mean() - midpoint.rolling(window=34).mean()


def calculate_williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算威廉指标 (Williams %R)。

    输入:
        df: 包含 'high', 'low', 'close' 的 DataFrame。

    输出:
        pd.Series: -100 到 0 的刻度。

    执行逻辑与解读:
        1. 快速随机指标的逆向版本。
        2. LLM 决策行动 (LLM Action):
           - > -20: 超买 (Overbought)。
           - < -80: 超卖 (Oversold)。
    """
    highest = df['high'].rolling(window=period).max()
    lowest = df['low'].rolling(window=period).min()
    return -100 * (highest - df['close']) / (highest - lowest).replace(0, 0.001)


def calculate_roc(df: pd.DataFrame, period: int = 9) -> pd.Series:
    """
    计算变动率 (Rate of Change, ROC)。

    输入:
        df: 包含 'close' 的 DataFrame。

    输出:
        pd.Series: 百分比变化。

    执行逻辑与解读:
        1. 纯粹的价格速度。
        2. LLM 决策行动 (LLM Action): 高 ROC 意味着强劲的脉冲。背离意味着动能衰竭。
    """
    return (df['close'] - df['close'].shift(period)) / df['close'].shift(period).replace(0, 0.001) * 100
