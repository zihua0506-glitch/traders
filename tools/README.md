# Tools - 量化分析工具目录

## 三层架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Layer 3: 资金管理层                        │
│  position_sizing.py  — 仓位计算 (固定风险/Kelly/波动率调整)   │
├──────────────────────────────────────────────────────────────┤
│                    Layer 2: 交易决策层                        │
│  entry_signal.py  — 多维评分 + 入场区间 + 动态止损/止盈      │
├──────────────────────────────────────────────────────────────┤
│                    Layer 1: 市场分析层                        │
│  smart_money  trend_structure  market_psychology              │
│  votality_risk  macro_lines  alpha                            │
├──────────────────────────────────────────────────────────────┤
│                    Layer 0: 基础工具层                        │
│  calculate.py (数据加载+比较函数)  function_list.py (公式库)  │
└──────────────────────────────────────────────────────────────┘
```

**统一函数签名** (Layer 1):
```python
function_name(symbol: str, optional_symbol: str = None) -> str
```
返回值均为 LLM 可直接理解的相对值分析字符串。

## 数据架构

数据源: `sentiment.db` → `stock_price_bars` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | VARCHAR | 股票代码 |
| interval | VARCHAR | 时间粒度 (`15m` / `1d`) |
| ts | INTEGER | Unix 时间戳 |
| open/high/low/close | FLOAT | OHLC 价格 |
| volume | INTEGER | 成交量 |

**重要**: `interval='1d'` 数据不准确，所有模块以 `15m` 为准，日线通过 `resample_daily()` 聚合。

两个时间维度:
- **微观 (Micro)**: 过去 24 小时 15min K线 (~96根)，用于入场/出场信号
- **宏观 (Macro)**: 日线聚合，用于 MA200 等大趋势判断

---

## Layer 1: 市场分析层

> 用途：读懂市场当前状态，为 Layer 2 提供输入信号。

### smart_money.py — 机构资金流向
主函数: `smart_money(symbol, optional_symbol) -> str`

追踪聪明钱的行为痕迹，判断机构是在吸筹还是在出货。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| VWAP | 机构平均成本线 | 价格 > VWAP = 多头控盘 |
| MFI | 带量权重的 RSI | > 80 超买, < 20 超卖, 顶背离 = 暴跌预警 |
| CMF | 资金进出压力 | > 0.05 吸筹, < -0.05 派发 |
| MACD | 趋势动量 | 金叉/死叉, 零轴位置, 柱状图方向 |

---

### trend_structure.py — 市场结构
主函数: `trend_structure(symbol, optional_symbol) -> str`

确定当前的市场背景（Context），"顺势而为"。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| Ichimoku | 多周期趋势系统 | TK 交叉 = 买卖信号, 价格 vs Kijun基准线 |
| SuperTrend | 趋势跟踪过滤器 | Close > ST = 只做多, Close < ST = 只做空 |
| Parabolic SAR | 反转检测 | SAR 跳到价格上方 = 立即离场 |

输出含: 支撑/阻力位、微观/宏观多周期一致性判断。

---

### market_psychology.py — 市场情绪
主函数: `market_psychology(symbol, optional_symbol) -> str`

捕捉贪婪与恐慌极端，寻找反转点。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| Williams %R | 快速超买超卖 | > -20 超买, < -80 超卖 |
| CCI | 统计偏离度 | > +100 超买, < -100 超卖, ±200 = 极端 |
| RSI | 相对强弱 | > 70 超买, < 30 超卖, 背离 = 最强反转信号 |

**多指标共振**: ≥2个同时超买/超卖 = 高置信度信号。

---

### votality_risk.py — 风控与波动
主函数: `volatility_risk(symbol, optional_symbol) -> str`

低波动 = 变盘前兆，高波动 = 趋势进行中。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| Keltner Channels | ATR 波动带 | 突破上轨 = 真突破, 跌破下轨 = 真跌破 |
| TTM Squeeze | 波动率压缩 | Squeeze ON = 暴风雨前的宁静 |
| CHOP | 震荡/趋势区分 | > 61.8 震荡市, < 38.2 趋势市 |
| ATR | 绝对波动幅度 | 止损参考 = ±2×ATR |

---

### macro_lines.py — 宏观均线
主函数: `macro_lines(symbol, optional_symbol) -> str`

宏观均线是市场的"大方向标"。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| MA200 | 年度趋势线 | 价格 > MA200 = 牛市 |
| MA50 | 季度趋势线 | MA50 上穿 MA200 = 黄金交叉 |
| EMA21 | 短期动态均线 | 价格回踩 EMA21 = 买点 |
| EMA169 | 中期动态均线 | EMA21 > EMA169 = 中期多头 |

---

### alpha.py — 量化 Alpha 因子
主函数: `alpha_factors(symbol, optional_symbol) -> str`

进阶量化因子，区别于传统技术指标（14个因子）。

| 类别 | 因子 | 用途 |
|------|------|------|
| 统计分布 | Z-Score, TS-Rank, 偏度, 峰度 | 均值回归 / 尾部风险 |
| 动量结构 | 加速度, K线强度, 效率比, 持续性 | 动能衰竭 / 趋势纯度 |
| 复杂性 | Hurst 指数, Shannon 熵 | 趋势 vs 均值回归 / 混乱度 |
| 量价 | 量价相关, WQ006, 量比, VWAP偏离 | 背离检测 / 突破验证 |

---

## Layer 2: 交易决策层

> 用途：聚合所有分析信号，给出具体的入场/止损/止盈方案。

### entry_signal.py — 入场信号聚合
主函数: `entry_signal(symbol) -> str`

多维度加权评分 + 具体入场区间 + 动态止损/止盈。

**评分体系 (满分 ±100)**:

| 维度 | 最高分 | 信号来源 |
|------|--------|---------|
| 趋势结构 | ±35 | SuperTrend(±20) + SAR(±10) + Ichimoku(±5) |
| 资金动量 | ±30 | MACD(±12) + CMF(±10) + VWAP位置(±8) |
| 情绪极值 | ±20 | RSI背离(±12) + RSI极值(±5) + Williams%R(±3) |
| 宏观背景 | ±15 | MA200(±10) + MA50(±5) |
| CHOP修正 | — | 趋势市 ×1.2 / 震荡市 ×0.7 |

**方向判断**: `|score| ≥ 65` 高置信度 / `40~65` 中置信度 / `< 40` 观望

**三种入场策略**:
- 市价入场 — 信号极强时立即执行
- 回踩入场 — 等待 VWAP/SuperTrend 支撑，R/R 更优
- 突破入场 — 确认突破近期高/低点，最可靠

**四种止损方法**:
1. ATR止损 — 价格 ± 2×ATR
2. 结构止损 — SuperTrend轨道 + 摆动极值 + 缓冲 (推荐)
3. VWAP止损 — VWAP ± 缓冲
4. 百分比止损 — 固定 1% / 2% / 3%

**动态止盈 R/R**:
- 趋势市: 1.5R / 3R / 5R
- 过渡期: 1R / 2R / 3.5R
- 震荡市: 0.8R / 1.5R / 2.5R
- ATR偏高 ×0.85 / ATR偏低 ×1.15

---

## Layer 3: 资金管理层

> 用途：在确定入场方向后，计算合理的仓位大小。

### position_sizing.py — 仓位管理
主函数: `position_size(symbol, account_equity, entry_price, stop_loss, risk_pct=0.01, win_rate=None, avg_rr=None) -> str`

**三种仓位模型**:

| 模型 | 公式 | 适用场景 |
|------|------|---------|
| ① 固定风险 | 数量 = (账户×风险%) / 止损距离 | 最常用，每笔固定亏 N% |
| ② 波动率调整 | 在固定风险基础上，按当前ATR相对均值缩放 | 高波动减仓，低波动加仓 |
| ③ Kelly公式 | f* = W - (1-W)/R，实际用半Kelly | 有回测数据时使用 |

```python
# 基本调用
from trader.tools.position_sizing import position_size

result = position_size(
    symbol="AAPL",
    account_equity=10000,   # 账户权益
    entry_price=185.00,     # 入场价
    stop_loss=182.50,       # 止损价
    risk_pct=0.01,          # 单笔风险 1%
)

# 含 Kelly (需要历史回测数据)
result = position_size(
    "AAPL", 10000, 185.00, 182.50,
    risk_pct=0.01,
    win_rate=0.55,  # 历史胜率 55%
    avg_rr=2.0,     # 历史平均盈亏比 1:2
)
```

---

## Layer 0: 基础工具层

### calculate.py — 比较工具库

**数据加载**:
| 函数 | 作用 |
|------|------|
| `load_bars(symbol)` | 从 DB 加载 K线，自动回退粒度 |
| `resample_daily(df)` | 15min 聚合为日线 |
| `get_recent_24h(df)` | 取最近 24 小时数据 |
| `get_concrete_price(symbol)` | 获取 VWAP/ATR/止损止盈具体数值 |

**相对值比较**:
| 函数 | 作用 |
|------|------|
| `above_below()` | "高于/低于 N%" 描述 |
| `range_position()` | 区间定位 (0-100%) |
| `sigma_position()` | 标准差位置 (几个 σ) |
| `classify_level()` | 阈值分类 (超买/超卖等) |
| `trend_direction()` | 趋势方向 + 强度 (线性回归斜率) |

**信号检测**:
| 函数 | 作用 |
|------|------|
| `cross_detect()` | 金叉 / 死叉 |
| `divergence_detect()` | 顶背离 / 底背离 |
| `extreme_detect()` | 24h 新高/新低 |
| `multi_timeframe_alignment()` | 微观/宏观一致性 |
| `support_resistance_relation()` | 支撑阻力关系 |

**情绪数据**:
| 函数 | 作用 |
|------|------|
| `load_sentiment(symbol, hours)` | 加载社交媒体情绪聚合 |
| `format_sentiment_report()` | 生成情绪报告字符串 |

### function_list.py — 底层公式库

所有底层计算函数的完整实现 (30个)，含 LLM 决策指南注释:
- **波动率** (5个): ATR, Garman-Klass, Parkinson, BB Width, Historical Vol
- **成交量** (6个): OBV, CMF, MFI, Force Index, Rolling VWAP, Volume Z-Score
- **Alpha 因子** (14个): Z-Score, 量价相关, K线强度, 加速度, TS-Rank 等
- **动量** (5个): Stochastic RSI, TSI, Awesome Oscillator, Williams %R, ROC

---

## 完整调用示例

```python
# ── Layer 1: 市场分析 ────────────────────────────────────────
from trader.tools.smart_money import smart_money
from trader.tools.trend_structure import trend_structure
from trader.tools.market_psychology import market_psychology
from trader.tools.votality_risk import volatility_risk
from trader.tools.macro_lines import macro_lines
from trader.tools.alpha import alpha_factors

print(smart_money("AAPL"))
print(trend_structure("AAPL", "SPY"))   # 含对比分析
print(market_psychology("NVDA"))
print(volatility_risk("TSLA"))
print(macro_lines("AAPL"))
print(alpha_factors("BTC"))

# ── Layer 2: 入场决策 ────────────────────────────────────────
from trader.tools.entry_signal import entry_signal

signal = entry_signal("AAPL")
print(signal)
# 输出: 综合评分/方向/入场区间/四种止损/动态止盈

# ── Layer 3: 仓位管理 ────────────────────────────────────────
from trader.tools.position_sizing import position_size

sizing = position_size(
    symbol="AAPL",
    account_equity=10000,
    entry_price=185.00,
    stop_loss=182.50,       # 来自 entry_signal 的结构止损
    risk_pct=0.01,
    win_rate=0.55,          # 可选，有回测数据时填入
    avg_rr=2.0,
)
print(sizing)
```

详见 [prompt.md](prompt.md) — 完整的 LLM 调用示范 prompt。
