---
name: quant-analysis
description: 量化交易综合分析工具。当用户想分析股票或虚拟货币的交易机会时使用，包括资金流向、趋势结构、市场情绪、波动率风控、宏观均线、Alpha因子等。触发词包括"分析"、"交易"、"买卖"、"做多"、"做空"、"预测"、"行情"、"K线"以及任何股票代码或虚拟货币代码。
---

# 量化交易综合分析工具

一套 LLM 驱动的量化分析 CLI 工具集，遵循**"情绪先行，价量验证"**原则。所有工具从 `sentiment.db` 读取 15min OHLCV K线数据，输出中文相对值分析报告。

## CLI 调用方式

所有工具在 `tools/` 目录下，统一参数格式：

```bash
python tools/<module>.py <SYMBOL> [--vs <对比标的>]
```

### 1. smart_money.py — 机构资金流向

追踪聪明钱行为，判断机构在吸筹还是出货。

```bash
python tools/smart_money.py NVDA
python tools/smart_money.py NVDA --vs SPY
```

**指标**: VWAP (机构成本线), MFI (带量RSI), CMF (资金进出), MACD (动量)

### 2. trend_structure.py — 市场趋势结构

判断当前多头/空头环境，提供支撑阻力位和多周期一致性。

```bash
python tools/trend_structure.py AAPL
python tools/trend_structure.py AAPL --vs SPY
```

**指标**: Ichimoku (多周期趋势), SuperTrend (趋势过滤器), Parabolic SAR (反转检测)

### 3. market_psychology.py — 市场情绪

捕捉贪婪与恐慌的极端情绪，寻找反转点。

```bash
python tools/market_psychology.py TSLA
python tools/market_psychology.py TSLA --vs QQQ
```

**指标**: Williams %R, CCI, RSI | 核心输出: 多指标共振超买/超卖 + 背离信号

### 4. votality_risk.py — 波动率与风控

分析波动率状态，区分震荡市/趋势市，提供止损建议。

```bash
python tools/votality_risk.py AAPL
python tools/votality_risk.py AAPL --vs SPY
```

**指标**: Keltner Channels, TTM Squeeze, CHOP, ATR | 核心输出: Squeeze 变盘信号 + ±2×ATR 止损

### 5. macro_lines.py — 宏观均线

判断牛熊分界和均线排列，需要至少 50 日数据。

```bash
python tools/macro_lines.py AAPL
python tools/macro_lines.py NVDA --vs SPY
```

**指标**: MA200 (年度), MA50 (季度), EMA21 (短期), EMA169 (中期) | 核心输出: 黄金/死亡交叉 + 均线排列

### 6. alpha.py — 量化 Alpha 因子

14 个进阶量化因子，覆盖统计分布、动量结构、复杂性、量价互动。

```bash
python tools/alpha.py NVDA
python tools/alpha.py AMD --vs INTC
```

**因子**: Z-Score, Hurst, 效率比, 香农熵, 偏度/峰度, 量比, VWAP偏离等

## 情绪驱动的工具选择

不要每次全量运行 6 个工具，根据情绪得分按需选择：

| 情绪状态 | 得分范围 | 必调工具 | 思路 |
|---------|---------|---------|------|
| 极度看多 | > 0.5 | market_psychology + smart_money | 警惕过热，查超买和出货 |
| 偏多 | 0.15 ~ 0.5 | macro_lines + trend_structure | 确认趋势和资金支持 |
| 中性 | -0.15 ~ 0.15 | votality_risk + alpha | 判断是否即将变盘 |
| 偏空 | -0.5 ~ -0.15 | market_psychology + trend_structure | 找超卖反弹机会 |
| 极度看空 | < -0.5 | market_psychology + smart_money + macro_lines | 检查恐慌底 |
| 数据不足 | < 5 条 | 全部 6 个 | 纯技术面分析 |

## 完整分析流程示例

```bash
# Step 1: 获取情绪和价位（通过 Python）
python -c "from tools.calculate import format_sentiment_report, get_concrete_price; print(format_sentiment_report('NVDA')); print(get_concrete_price('NVDA'))"

# Step 2: 假设情绪偏多，确认趋势+资金
python tools/macro_lines.py NVDA
python tools/trend_structure.py NVDA
python tools/smart_money.py NVDA

# Step 3: 如需深度分析
python tools/alpha.py NVDA
python tools/market_psychology.py NVDA
python tools/votality_risk.py NVDA
```

## 输出格式要求

最终报告必须包含：

1. **情绪概览**: 得分、看多/看空比例、关键观点
2. **技术面验证**: 调用了哪些工具、核心发现、信号一致性/矛盾
3. **综合判断**: 方向 (看多/看空/观望) + 置信度 (高/中/低) + 核心依据
4. **具体操作建议** (必须有确切数值): 当前价 / VWAP / 入场价 / 硬止损(2×ATR) / 止盈(1.5~3×ATR)
5. **风险提示**: 失效因素 + 有效时间框架 (通常 2-4 小时)

## 关键原则

- **背离优先级最高**: RSI/MFI/CCI 出现背离，无论情绪如何都要警惕反转
- **情绪反转思维**: 极端看多时查超买，极端看空时查超卖
- **两周期必须结合**: 宏观(日线) vs 微观(15min) 交叉验证
- **数值必须具体**: 止损/止盈/入场价必须是确切的美元值
