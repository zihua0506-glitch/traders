# Tools - 量化分析工具目录

## 核心设计

每个 py 文件是一个独立的分析模块，主函数签名统一为：
```python
function_name(symbol: str, optional_symbol: str = None) -> str
```
- `symbol`: 主标的代码 (如 `'AAPL'`)
- `optional_symbol`: 可选的对比标的 (如 `'SPY'`)，用于相对强弱比较
- 返回值: LLM 可直接理解的相对值分析字符串

## 数据架构

数据源: `sentiment.db` → `stock_price_bars` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | VARCHAR | 股票代码 |
| interval | VARCHAR | 时间粒度 (`15m` / `1d`) |
| ts | INTEGER | Unix 时间戳 |
| open/high/low/close | FLOAT | OHLC 价格 |
| volume | INTEGER | 成交量 |

**重要**: `interval='1d'` 的数据不准确，所有程序以 `15m` 数据为准。日线数据通过 `resample_daily()` 从 15min 聚合生成。

两个时间维度:
- **微观 (Micro)**: 过去 24 小时的 15 分钟 K 线 (~96 根)，用于精确的入场/出场信号
- **宏观 (Macro)**: 从 15min 聚合的日线数据，用于判断大趋势方向 (MA200 等)

输出原则: **只比较相对值** (因为 LLM 对绝对值不敏感)，使用"高于/低于"、"金叉/死叉"、"偏离 N 个标准差"等描述。

---

## 分析模块

### smart_money.py — 机构资金流向
主函数: `smart_money(symbol, optional_symbol) -> str`

追踪聪明钱的行为痕迹，判断机构是在吸筹还是在出货。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| VWAP | 机构平均成本线 | 价格 > VWAP = 多头控盘 |
| MFI | 带量权重的 RSI | > 80 超买, < 20 超卖, 顶背离 = 暴跌预警 |
| CMF | 资金进出压力 | > 0 吸筹, < 0 派发 |
| MACD | 趋势动量 | 金叉/死叉, 零轴位置, 柱状图方向 |

### trend_structure.py — 市场结构
主函数: `trend_structure(symbol, optional_symbol) -> str`

确定当前的市场背景（Context），"顺势而为"。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| Ichimoku | 多周期趋势系统 | TK 交叉 = 买卖信号, 价格 vs 基准线 |
| SuperTrend | 趋势跟踪过滤器 | Close > ST = 只做多, Close < ST = 只做空 |
| Parabolic SAR | 反转检测 | SAR 跳到价格上方 = 立即离场 |

输出包含: 支撑/阻力位关系、微观/宏观多周期一致性判断。

### market_psychology.py — 市场情绪
主函数: `market_psychology(symbol, optional_symbol) -> str`

捕捉人类交易者的非理性情绪（贪婪与恐慌），寻找反转点。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| Williams %R | 快速超买超卖 | > -20 超买, < -80 超卖 |
| CCI | 统计偏离度 | > +100 超买, < -100 超卖, ±200 = 极端 |
| RSI | 相对强弱 | > 70 超买, < 30 超卖, 背离 = 最强反转信号 |

输出包含: 多指标共振判断（2 个以上同时超买/超卖 = 高置信度）、背离汇总。

### volatility_risk.py — 风控与波动
主函数: `volatility_risk(symbol, optional_symbol) -> str`

波动率 = 风险的代名词。低波动 = 即将变盘，高波动 = 趋势进行中。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| Keltner Channels | ATR 波动带 | 突破上轨 = 真突破, 跌破下轨 = 真跌破 |
| TTM Squeeze | 波动率压缩 | Squeeze ON = 暴风雨前的宁静 |
| CHOP | 震荡/趋势区分 | > 61.8 震荡市, < 38.2 趋势市 |
| ATR | 绝对波动幅度 | 止损建议 = ±2×ATR |

### macro_lines.py — 宏观均线
主函数: `macro_lines(symbol, optional_symbol) -> str`

宏观均线是市场的"大方向标"。

| 指标 | 作用 | 关键信号 |
|------|------|----------|
| MA200 | 年度趋势线 | 价格 > MA200 = 牛市 |
| MA50 | 季度趋势线 | MA50 上穿 MA200 = 黄金交叉 |
| EMA21 | 短期动态均线 | 价格回踩 EMA21 = 买点 |
| EMA169 | 中期动态均线 | EMA21 > EMA169 = 中期多头 |

输出包含: 均线排列顺序、乖离率对比、短长期一致性判断。

### alpha.py — 量化 Alpha 因子
主函数: `alpha_factors(symbol, optional_symbol) -> str`

进阶量化因子，区别于传统技术指标。

| 类别 | 因子 | 用途 |
|------|------|------|
| 统计分布 | Z-Score, TS-Rank, 偏度, 峰度 | 均值回归 / 尾部风险 |
| 动量结构 | 加速度, K线强度, 效率比, 持续性 | 动能衰竭 / 趋势纯度 |
| 复杂性 | Hurst 指数, Shannon 熵 | 趋势 vs 均值回归 / 混乱度 |
| 量价 | 量价相关, WQ006, 量比, VWAP偏离 | 背离检测 / 突破验证 |

---

## 工具模块

### calculate.py — 比较工具库
提供 LLM 友好的相对值比较函数:

| 函数 | 作用 |
|------|------|
| `load_bars()` | 从 DB 加载 K线数据 (自动回退最佳粒度) |
| `resample_daily()` | 短周期聚合为日线 |
| `get_recent_24h()` | 取最近 24 小时数据 |
| `pct_diff()` | 百分比差异 |
| `above_below()` | "高于/低于" 描述 |
| `range_position()` | 区间定位 (0-100%) |
| `sigma_position()` | 标准差位置 (几个 σ) |
| `classify_level()` | 阈值分类 (超买/超卖等) |
| `trend_direction()` | 趋势方向 + 强度 |
| `cross_detect()` | 金叉 / 死叉检测 |
| `divergence_detect()` | 顶背离 / 底背离检测 |
| `rate_of_change()` | 变动率 + 加速减速 |
| `compare_symbols()` | 双标的对比 |
| `multi_timeframe_alignment()` | 微观/宏观一致性 |
| `extreme_detect()` | 24h 新高/新低 |
| `support_resistance_relation()` | 支撑阻力关系 |
| `load_sentiment()` | 加载情绪聚合数据 (按标的+时间窗口) |
| `format_sentiment_report()` | 生成 LLM 可读的情绪报告 |
| `get_concrete_price()` | 获取关键价格水平 (VWAP/ATR/止损止盈) |

### function_list.py — 函数文档与实现
所有底层计算函数的完整实现和 LLM 决策指南，分 4 大类:
- **波动率** (5个): ATR, Garman-Klass, Parkinson, BB Width, Historical Vol
- **成交量** (6个): OBV, CMF, MFI, Force Index, Rolling VWAP, Volume Z-Score
- **Alpha 因子** (14个): Z-Score, 量价相关, K线强度, 加速度, TS-Rank 等
- **动量** (5个): Stochastic RSI, TSI, Awesome Oscillator, Williams %R, ROC

---

## 调用示例

详见 [prompt.md](prompt.md) — 完整的 LLM 调用示范 prompt。

```python
# 快速调用
from trader.tools.smart_money import smart_money
from trader.tools.trend_structure import trend_structure
from trader.tools.market_psychology import market_psychology
from trader.tools.votality_risk import volatility_risk
from trader.tools.macro_lines import macro_lines
from trader.tools.alpha import alpha_factors

# 单标的分析
print(smart_money("AAPL"))
print(trend_structure("AAPL"))

# 对比分析
print(market_psychology("NVDA", "SPY"))
print(alpha_factors("TSLA", "QQQ"))
```
