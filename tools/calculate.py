"""
calculate.py - 比较值之间的大小的函数

核心思想: LLM 对绝对值不敏感，但对相对比较（如"高于"、"偏离2个标准差"、"金叉"等）非常敏感。
本模块提供:
1. 数据加载 (从 sentiment.db 读取 15min K线)
2. 相对值比较函数 (百分比差、趋势方向、交叉检测、背离检测等)
3. 报告格式化 (将指标汇总为 LLM 可读的字符串)
"""

import sqlite3
import os
import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sentiment.db')


# ==========================================
# 1. 数据加载
# ==========================================

def load_bars(symbol: str, interval: str = '15m', limit: int = 20000) -> pd.DataFrame:
    """
    从 sentiment.db 加载 OHLCV 数据。

    Parameters:
        symbol: 股票代码 (如 'AAPL')
        interval: 时间粒度 (默认 '15m')。
                  如果指定 interval 不存在，自动回退到可用的最佳粒度:
                  优先级: 15m > 5m > 2m > 1m > 1d
        limit: 最大行数

    Returns:
        pd.DataFrame: 包含 open, high, low, close, volume 列，以 datetime 为索引
    """
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT ts, open, high, low, close, volume
        FROM stock_price_bars
        WHERE symbol = ? AND interval = ?
        ORDER BY ts DESC
        LIMIT ?
    """
    df = pd.read_sql_query(query, conn, params=(symbol.upper(), interval, limit))

    # 如果指定 interval 无数据，自动回退到可用的最佳粒度
    if df.empty:
        fallback_order = ['15m', '5m', '2m', '1m']
        for fb_interval in fallback_order:
            if fb_interval == interval:
                continue
            df = pd.read_sql_query(query, conn, params=(symbol.upper(), fb_interval, limit))
            if not df.empty:
                break

    conn.close()

    if df.empty:
        return df

    df = df.sort_values('ts').reset_index(drop=True)
    df['datetime'] = pd.to_datetime(df['ts'], unit='s')
    df = df.set_index('datetime')
    return df


def resample_daily(df_15m: pd.DataFrame) -> pd.DataFrame:
    """
    将 15 分钟数据聚合为日线数据。
    用于计算 MA200 等宏观指标（因为 1d interval 数据不准确）。
    """
    if df_15m.empty:
        return df_15m
    daily = df_15m.resample('1D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    return daily


def get_recent_24h(df: pd.DataFrame) -> pd.DataFrame:
    """取最近 24 小时的数据 (约 96 根 15min K 线)。"""
    if df.empty:
        return df
    cutoff = df.index[-1] - pd.Timedelta(hours=24)
    return df[df.index >= cutoff]


# ==========================================
# 2. 百分比与差值比较
# ==========================================

def pct_diff(a: float, b: float) -> str:
    """
    计算百分比差异: (a - b) / |b| * 100。
    用途: 比较两个价格、两个指标值之间的相对大小。
    返回: "+2.35%" 或 "-1.47%"
    """
    try:
        if b == 0 or np.isnan(a) or np.isnan(b):
            return "N/A"
    except (TypeError, ValueError):
        return "N/A"
    diff = (a - b) / abs(b) * 100
    return f"{diff:+.2f}%"


def above_below(value: float, reference: float,
                value_name: str = "当前值", ref_name: str = "参考值") -> str:
    """
    描述 value 相对于 reference 的位置及偏离程度。
    用途: "价格 高于 VWAP +2.35%"
    """
    diff = pct_diff(value, reference)
    if value > reference:
        position = "高于"
    elif value < reference:
        position = "低于"
    else:
        position = "等于"
    return f"{value_name} {position} {ref_name} ({diff})"


# ==========================================
# 3. 区间定位
# ==========================================

def range_position(value: float, low: float, high: float) -> str:
    """
    描述 value 在 [low, high] 范围中的位置。
    用途: 判断价格在布林带/肯特纳通道中的位置。
    返回: "72.5% (偏高)"
    """
    try:
        if np.isnan(value) or np.isnan(low) or np.isnan(high):
            return "N/A (数据不足)"
    except (TypeError, ValueError):
        pass
    if high == low:
        return "50.0% (区间为零)"
    pos = (value - low) / (high - low) * 100
    pos = max(0.0, min(100.0, pos))

    if pos >= 80:
        label = "极高位"
    elif pos >= 60:
        label = "偏高"
    elif pos >= 40:
        label = "中间"
    elif pos >= 20:
        label = "偏低"
    else:
        label = "极低位"

    return f"{pos:.1f}% ({label})"


def sigma_position(value: float, mean: float, std: float) -> str:
    """
    描述值距均值多少个标准差 (σ)。
    用途: Z-Score 类指标的相对位置描述。
    返回: "+1.5σ (偏高)" 或 "-2.3σ (极端偏低)"
    """
    if std == 0:
        return "0σ (波动为零)"
    sigma = (value - mean) / std

    if abs(sigma) > 3:
        label = "极端"
    elif abs(sigma) > 2:
        label = "显著"
    elif abs(sigma) > 1:
        label = "偏离"
    else:
        label = "正常"

    direction = "偏高" if sigma > 0 else "偏低"
    return f"{sigma:+.2f}σ ({label}{direction})"


# ==========================================
# 4. 阈值分类
# ==========================================

def classify_level(value: float, thresholds: dict) -> str:
    """
    根据阈值将数值分类为标签。
    用途: 把 RSI=75 分类为 "超买"，MFI=15 分类为 "超卖"。

    Example:
        classify_level(75, {'超买': 80, '偏多': 60, '中性': 40, '偏空': 20, '超卖': 0})
        → "偏多"
    """
    sorted_levels = sorted(thresholds.items(), key=lambda x: x[1], reverse=True)
    for label, threshold in sorted_levels:
        if value >= threshold:
            return label
    return sorted_levels[-1][0]


# ==========================================
# 5. 趋势方向判断
# ==========================================

def trend_direction(series: pd.Series, window: int = 5) -> str:
    """
    基于线性回归斜率判断序列的趋势方向和强度。
    用途: "MFI 趋势: 上升 (强)"
    返回: "上升 (强)", "下降 (弱)", "横盘"
    """
    if len(series.dropna()) < max(window, 3):
        return "数据不足"

    recent = series.tail(window).dropna()
    if len(recent) < 3:
        return "数据不足"

    x = np.arange(len(recent))
    y = np.asarray(recent.values, dtype=np.float64)

    y_mean = np.mean(np.abs(y))
    if y_mean == 0:
        return "横盘"

    slope: float = float(np.polyfit(x, y, 1)[0])
    relative_slope = slope / y_mean * 100

    if abs(relative_slope) < 0.1:
        return "横盘"

    direction = "上升" if relative_slope > 0 else "下降"
    if abs(relative_slope) > 1.0:
        strength = "强"
    elif abs(relative_slope) > 0.3:
        strength = "中"
    else:
        strength = "弱"

    return f"{direction} ({strength})"


def slope_angle(series: pd.Series, window: int = 5) -> str:
    """
    计算序列斜率的角度描述。
    用途: 区分"急涨"和"缓涨"，对应不同的交易策略。
    返回: "陡峭上升 (45°+)", "缓慢下降 (<15°)"
    """
    if len(series.dropna()) < window:
        return "数据不足"

    recent = series.tail(window).dropna()
    if len(recent) < 2:
        return "数据不足"

    pct_change = (recent.iloc[-1] - recent.iloc[0]) / abs(recent.iloc[0]) * 100 if recent.iloc[0] != 0 else 0

    if abs(pct_change) > 5:
        return f"陡峭{'上升' if pct_change > 0 else '下降'} ({pct_change:+.1f}%)"
    elif abs(pct_change) > 1:
        return f"稳步{'上升' if pct_change > 0 else '下降'} ({pct_change:+.1f}%)"
    elif abs(pct_change) > 0.2:
        return f"缓慢{'上升' if pct_change > 0 else '下降'} ({pct_change:+.1f}%)"
    else:
        return f"横盘 ({pct_change:+.1f}%)"


# ==========================================
# 6. 交叉检测
# ==========================================

def cross_detect(fast: pd.Series, slow: pd.Series) -> str:
    """
    检测快线是否刚穿越慢线 (金叉/死叉)。
    用途: MACD 交叉、均线交叉、Ichimoku TK Cross。
    返回: "金叉 (看多)", "死叉 (看空)", "多头排列", "空头排列"
    """
    fast_clean = fast.dropna()
    slow_clean = slow.dropna()

    if len(fast_clean) < 2 or len(slow_clean) < 2:
        return "数据不足"

    # 对齐索引
    common = fast_clean.index.intersection(slow_clean.index)
    if len(common) < 2:
        return "数据不足"

    f = fast_clean.loc[common]
    s = slow_clean.loc[common]

    prev_diff = f.iloc[-2] - s.iloc[-2]
    curr_diff = f.iloc[-1] - s.iloc[-1]

    if prev_diff <= 0 and curr_diff > 0:
        return "金叉 (看多)"
    elif prev_diff >= 0 and curr_diff < 0:
        return "死叉 (看空)"
    elif curr_diff > 0:
        return "快线在上 (多头排列)"
    else:
        return "快线在下 (空头排列)"


# ==========================================
# 7. 背离检测
# ==========================================

def divergence_detect(price: pd.Series, indicator: pd.Series, window: int = 14) -> str:
    """
    检测价格与指标之间的背离。
    用途: RSI 背离、MFI 背离、OBV 背离 —— 最强的反转预警信号之一。

    顶背离 (Bearish Divergence): 价格新高 + 指标未新高 → 看跌
    底背离 (Bullish Divergence): 价格新低 + 指标未新低 → 看涨

    返回: "顶背离 (看跌信号)", "底背离 (看涨信号)", "无背离"
    """
    if len(price) < window or len(indicator) < window:
        return "数据不足"

    price_recent = price.tail(window)
    ind_recent = indicator.tail(window)

    half = window // 2

    price_first = price_recent.iloc[:half]
    price_second = price_recent.iloc[half:]
    ind_first = ind_recent.iloc[:half]
    ind_second = ind_recent.iloc[half:]

    # 顶背离: 价格后半段创新高，但指标后半段未创新高
    if price_second.max() > price_first.max() and ind_second.max() < ind_first.max():
        return "顶背离 (看跌信号)"

    # 底背离: 价格后半段创新低，但指标后半段未创新低
    if price_second.min() < price_first.min() and ind_second.min() > ind_first.min():
        return "底背离 (看涨信号)"

    return "无背离"


# ==========================================
# 8. 变动率与动量比较
# ==========================================

def rate_of_change(series: pd.Series, periods: int = 1) -> str:
    """
    计算变动率并描述动量状态。
    用途: 判断指标是在加速还是减速变化。
    返回: "+3.25% (加速上涨)" 或 "-1.10% (减速下跌)"
    """
    if len(series.dropna()) < periods + 1:
        return "数据不足"

    s = series.dropna()
    current = s.iloc[-1]
    previous = s.iloc[-1 - periods]

    if previous == 0:
        return "N/A"

    roc = (current - previous) / abs(previous) * 100

    # 判断加速/减速
    if len(s) >= periods * 2 + 1:
        prev_prev = s.iloc[-1 - periods * 2]
        if prev_prev != 0:
            prev_roc = (previous - prev_prev) / abs(prev_prev) * 100
            if roc > 0 and roc > prev_roc:
                momentum = "加速上涨"
            elif roc > 0:
                momentum = "减速上涨"
            elif roc < 0 and roc < prev_roc:
                momentum = "加速下跌"
            elif roc < 0:
                momentum = "减速下跌"
            else:
                momentum = "持平"
        else:
            momentum = "上涨" if roc > 0 else "下跌"
    else:
        momentum = "上涨" if roc > 0 else "下跌"

    return f"{roc:+.2f}% ({momentum})"


# ==========================================
# 9. 双标的对比
# ==========================================

def compare_symbols(val_a: float, val_b: float,
                    symbol_a: str, symbol_b: str, indicator: str) -> str:
    """
    比较两个标的同一指标的值。
    用途: "AAPL 的 RSI (65.2) 强于 SPY 的 RSI (52.3)"
    """
    diff = val_a - val_b
    stronger = symbol_a if val_a > val_b else symbol_b
    return (f"{symbol_a} {indicator}={val_a:.2f} vs "
            f"{symbol_b} {indicator}={val_b:.2f}, "
            f"{stronger} 更强 (差值 {diff:+.2f})")


# ==========================================
# 10. 多周期一致性检查
# ==========================================

def multi_timeframe_alignment(micro_signal: str, macro_signal: str) -> str:
    """
    检查微观 (15min) 和宏观 (日线) 信号是否一致。
    用途: 只有两个时间周期信号一致时才应该入场。

    返回: "一致看多 (强信号)", "微观看多/宏观看空 (矛盾，谨慎)"
    """
    micro_bull = any(k in micro_signal for k in ["看多", "多头", "上升", "金叉", "超卖"])
    micro_bear = any(k in micro_signal for k in ["看空", "空头", "下降", "死叉", "超买"])
    macro_bull = any(k in macro_signal for k in ["看多", "多头", "上升", "金叉", "超卖"])
    macro_bear = any(k in macro_signal for k in ["看空", "空头", "下降", "死叉", "超买"])

    if micro_bull and macro_bull:
        return "一致看多 (强信号)"
    elif micro_bear and macro_bear:
        return "一致看空 (强信号)"
    elif micro_bull and macro_bear:
        return f"微观看多 / 宏观看空 (矛盾，谨慎)"
    elif micro_bear and macro_bull:
        return f"微观看空 / 宏观看多 (矛盾，谨慎)"
    else:
        return "信号不明确 (观望)"


# ==========================================
# 11. 极值检测
# ==========================================

def extreme_detect(series: pd.Series, window: int = 96) -> str:
    """
    检测当前值是否处于近期极值。
    window=96 约等于 24 小时的 15min 数据。
    用途: 检测价格是否在 24h 内创新高/新低。
    返回: "24h 新高", "24h 新低", "区间内"
    """
    if len(series.dropna()) < window:
        return "数据不足"

    recent = series.tail(window).dropna()
    current = recent.iloc[-1]

    if current >= recent.max():
        return "24h 新高"
    elif current <= recent.min():
        return "24h 新低"
    else:
        pos = range_position(current, recent.min(), recent.max())
        return f"区间内 ({pos})"


# ==========================================
# 12. 支撑阻力关系
# ==========================================

def support_resistance_relation(price: float, support: float, resistance: float) -> str:
    """
    描述当前价格与支撑/阻力位的关系。
    用途: "价格距支撑 +1.2%, 距阻力 -3.5%"
    """
    dist_support = pct_diff(price, support)
    dist_resistance = pct_diff(price, resistance)
    sr_range = range_position(price, support, resistance)
    return f"距支撑位 {dist_support}, 距阻力位 {dist_resistance}, 位置: {sr_range}"


# ==========================================
# 13. 报告格式化
# ==========================================

def format_report(title: str, sections: list) -> str:
    """
    将多个指标段落格式化为一个 LLM 报告字符串。
    sections: list of (indicator_name, description_str)
    """
    lines = [f"=== {title} ==="]
    for name, desc in sections:
        lines.append(f"[{name}] {desc}")
    return "\n".join(lines)


# ==========================================
# 14. 情绪数据聚合
# ==========================================

def load_sentiment(symbol: str, hours: int = 24) -> dict:
    """
    从 sentiment.db 加载某标的在指定时间窗口内的情绪聚合数据。

    Parameters:
        symbol: 股票代码 (如 'AAPL')
        hours: 回溯时间窗口 (小时)

    Returns:
        dict: {
            'total': int,
            'bullish': int, 'bearish': int, 'neutral': int,
            'bull_ratio': float, 'bear_ratio': float,
            'weighted_score': float,  # engagement-weighted: +1 bull, -1 bear
            'top_summaries': list[str],  # 高互动帖子摘要
            'avg_engagement': float,
            'sentiment_label': str,  # '偏多' / '偏空' / '中性' / '极度看多' / '极度看空'
        }
    """
    import time as _time
    conn = sqlite3.connect(DB_PATH)
    cutoff_ts = int(_time.time()) - hours * 3600

    # SQLite JSON: tickers 字段是 JSON 数组, 用 LIKE 做简单匹配
    # 更精确的方式是 json_each, 但 LIKE 对 '["AAPL", "MSFT"]' 这类格式足够
    query = """
        SELECT sentiment, summary, likes, comments, shares, views, post_time
        FROM sentimentpost
        WHERE post_time >= ?
          AND tickers LIKE ?
        ORDER BY (likes + comments + shares) DESC
    """
    pattern = f'%"{symbol.upper()}"%'
    rows = []
    try:
        cursor = conn.execute(query, (cutoff_ts, pattern))
        rows = cursor.fetchall()
    except Exception:
        # 表可能不存在或字段名不同，尝试备用表名
        try:
            query_alt = query.replace('sentimentpost', 'sentiment_post')
            cursor = conn.execute(query_alt, (cutoff_ts, pattern))
            rows = cursor.fetchall()
        except Exception:
            pass
    conn.close()

    total = len(rows)
    if total == 0:
        return {
            'total': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0,
            'bull_ratio': 0.0, 'bear_ratio': 0.0,
            'weighted_score': 0.0, 'top_summaries': [],
            'avg_engagement': 0.0, 'sentiment_label': '无数据',
        }

    bullish = sum(1 for r in rows if r[0] == 'bullish')
    bearish = sum(1 for r in rows if r[0] == 'bearish')
    neutral = total - bullish - bearish
    bull_ratio = bullish / total
    bear_ratio = bearish / total

    # engagement-weighted score: bullish=+1, bearish=-1, neutral=0
    # weight = likes + comments + shares + 1 (avoid zero)
    weighted_sum = 0.0
    total_weight = 0.0
    total_engagement = 0.0
    for r in rows:
        sentiment, summary, likes, comments, shares, views, post_time = r
        engagement = (likes or 0) + (comments or 0) + (shares or 0)
        weight = engagement + 1
        total_engagement += engagement
        total_weight += weight
        if sentiment == 'bullish':
            weighted_sum += weight
        elif sentiment == 'bearish':
            weighted_sum -= weight

    weighted_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    avg_engagement = total_engagement / total

    # label
    if weighted_score > 0.5:
        sentiment_label = '极度看多'
    elif weighted_score > 0.15:
        sentiment_label = '偏多'
    elif weighted_score < -0.5:
        sentiment_label = '极度看空'
    elif weighted_score < -0.15:
        sentiment_label = '偏空'
    else:
        sentiment_label = '中性'

    # top summaries (最高互动的前5条)
    top_summaries = [r[1] for r in rows[:5] if r[1]]

    return {
        'total': total,
        'bullish': bullish,
        'bearish': bearish,
        'neutral': neutral,
        'bull_ratio': bull_ratio,
        'bear_ratio': bear_ratio,
        'weighted_score': weighted_score,
        'top_summaries': top_summaries,
        'avg_engagement': avg_engagement,
        'sentiment_label': sentiment_label,
    }


def format_sentiment_report(symbol: str, hours: int = 24) -> str:
    """
    生成 LLM 可读的情绪分析报告。

    Returns:
        str: 格式化的情绪报告，包含比例、加权得分、关键观点
    """
    data = load_sentiment(symbol, hours)

    if data['total'] == 0:
        return f"=== {symbol} 情绪分析 (过去{hours}小时) ===\n无相关情绪数据"

    sections = [
        ("帖子统计", f"共 {data['total']} 条: "
                     f"看多 {data['bullish']}({data['bull_ratio']:.0%}), "
                     f"看空 {data['bearish']}({data['bear_ratio']:.0%}), "
                     f"中性 {data['neutral']}"),
        ("加权情绪", f"得分: {data['weighted_score']:+.3f}, "
                     f"判断: {data['sentiment_label']}, "
                     f"平均互动: {data['avg_engagement']:.0f}"),
    ]

    if data['top_summaries']:
        summaries_text = " | ".join(data['top_summaries'][:3])
        sections.append(("关键观点", summaries_text))

    return format_report(f"{symbol} 情绪分析 (过去{hours}小时)", sections)


def get_concrete_price(symbol: str) -> dict:
    """
    获取标的的关键价格水平 (具体数值)。
    用于最终输出中给出确切的止损/止盈/VWAP 等价格。

    Returns:
        dict: {
            'current_price': float,
            'vwap': float,
            'atr': float,
            'stop_loss_long': float,   # 做多止损 = price - 2*ATR
            'stop_loss_short': float,  # 做空止损 = price + 2*ATR
            'take_profit_long': float, # 做多止盈 = price + 3*ATR
            'take_profit_short': float,
            'high_24h': float,
            'low_24h': float,
        }
    """
    df = load_bars(symbol)
    if df.empty:
        return {}

    df_24h = get_recent_24h(df)
    if len(df_24h) < 20:
        df_24h = df.tail(96)

    close = df_24h['close'].iloc[-1]

    # VWAP
    v = df_24h['volume']
    tp = (df_24h['high'] + df_24h['low'] + df_24h['close']) / 3
    vwap = float((tp * v).cumsum().iloc[-1] / v.cumsum().iloc[-1])

    # ATR (14 period)
    high, low = df_24h['high'], df_24h['low']
    tr = pd.concat([
        high - low,
        (high - df_24h['close'].shift(1)).abs(),
        (low - df_24h['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().dropna().iloc[-1]) if len(tr.dropna()) >= 14 else float(tr.mean())

    return {
        'current_price': float(close),
        'vwap': round(vwap, 2),
        'atr': round(atr, 4),
        'stop_loss_long': round(close - 2 * atr, 2),
        'stop_loss_short': round(close + 2 * atr, 2),
        'take_profit_long': round(close + 3 * atr, 2),
        'take_profit_short': round(close - 3 * atr, 2),
        'high_24h': float(df_24h['high'].max()),
        'low_24h': float(df_24h['low'].min()),
    }
