---
name: swing-scout
description: 超短线股票机会扫描工具。当用户想进行超短线交易分析、扫描突发新闻驱动的交易机会、或要求完整的"社交媒体+新闻+量化"综合分析时使用。触发词包括"超短线分析"、"扫描机会"、"swing scout"、"今日机会"、"开盘分析"、"盘前分析"、"突发新闻分析"以及任何需要结合舆情和量化的超短线交易分析请求。
---

# 超短线机会扫描工具 (Swing Scout)

基于"**突发新闻驱动 + 量化验证**"的超短线分析流水线。聚焦纳斯达克100和标普500成分股中，受突发事件影响、尚未被市场完全定价的交易机会。

## 核心原则

- **只关注超短线**：最近数小时内的突发新闻，不做长线推演
- **只关注未定价事件**：周末/盘后发生的、下一个交易日开盘才会反映的事件
- **新闻先行，量化验证**：先确定"为什么会动"，再用技术面确认"怎么动"
- **结果全部落盘**：所有分析写入 `analysis_log/{YYYYMMDD_HHMM}.txt`

## 执行流程

### Phase 1: 社交媒体舆情采集

调用 social-media-scraper 抓取最新社交媒体数据：

```bash
python3 cli/social_media_cli.py --minutes 1440
```

分析输出，提取：

1. **关注列表**：哪些股票 symbol 被提及或受影响
2. **关注原因**：每个 symbol 为什么值得关注（用一句话概括）
3. **情绪方向**：社交媒体对该 symbol 的情绪倾向（利多/利空/争议）
4. **搜索计划**：后续需要在网上验证的关键问题列表

将以上内容写入 `analysis_log/{YYYYMMDD_HHMM}.txt`，格式：

```
=== SWING SCOUT REPORT ===
Date: {date}
Generated: {timestamp}

== Phase 1: Social Media Scan ==

[Symbol] REASON | SENTIMENT
  - Detail...

Search Plan:
  1. ...
  2. ...
```

### Phase 2: 突发新闻深度搜索

调用 browser-use (headed 模式) 逐条执行 Phase 1 的搜索计划：

**搜索策略**：
- Google 搜索限定最近 6-12 小时 (`tbs=qdr:h6` 或 `tbs=qdr:h12`)
- **必须打开文章详情页阅读**，不能只看搜索摘要
- 优先选择免费可读的来源：Guardian、BBC、Al Jazeera、Electrek、TechCrunch、Yahoo Finance
- 付费墙来源（Reuters、NYT、WSJ）只读搜索摘要，不尝试打开

**每条搜索需要确认**：
1. 事件的具体细节（不是模糊概括）
2. 事件发生的精确时间（是否在上一交易日收盘之后）
3. 是否已被市场定价（如果是盘中发生的，大概率已定价）
4. 对具体 symbol 的影响路径

**筛选标准 — 只保留满足以下条件的事件**：
- 发生在上一交易日收盘后（美东 4pm 后）
- 有明确的个股影响路径（不是泛泛的"利空大盘"）
- 有主流媒体报道（不只是社交媒体爆料）

将结果追加到报告文件：

```
== Phase 2: Breaking News Verification ==

[UNPRICED] Event description
  Source: {url}
  Time: {when it happened}
  Impact: {symbol} {direction} - {why}

[ALREADY PRICED] Event description
  Reason: happened during market hours / already reflected in Friday close

Final Watch List (unpriced events only):
  SYMBOL | DIRECTION | CATALYST | CONFIDENCE
```

### Phase 3: 数据获取

基于 Phase 2 筛选出的 symbol 列表，调用 stock-data 获取日线和分钟线数据（自动同步后返回 JSON）：

```bash
# 获取最近10个交易日的日线数据
python3 cli/stock_data.py daily {SYMBOLS} --days 10

# 获取最近60分钟的分钟线数据
python3 cli/stock_data.py minute {SYMBOLS} --minutes 60
```

同时拉取对应的基准指数：
- 如果关注个股多为科技股，加 QQQ
- 如果关注能源/国防股，加 SPY XLE

### Phase 4: 量化分析与仓位计算

对 Phase 2 筛选出的每个 symbol，**综合 Phase 1-3 的所有信息自主判断**该用哪些工具、以什么顺序执行。下面是可用工具清单和选择指南，不是固定流程——你需要像交易员一样思考，根据具体情况灵活组合。

#### 可用工具清单

| 工具 | 用途 | 何时用 |
|------|------|--------|
| `tools/smart_money.py` | 机构资金流向 (VWAP/MFI/CMF/MACD) | 想知道机构在吸筹还是出货 |
| `tools/trend_structure.py` | 趋势结构 (Ichimoku/SuperTrend/SAR) | 想确认趋势方向和支撑阻力 |
| `tools/market_psychology.py` | 情绪极值 (Williams%R/CCI/RSI) | 想知道是否超买超卖、有无背离 |
| `tools/votality_risk.py` | 波动率风控 (Keltner/TTM/CHOP/ATR) | 想判断震荡市还是趋势市、计算止损 |
| `tools/macro_lines.py` | 宏观均线 (MA200/MA50/EMA21/EMA169) | 想看牛熊分界和均线排列 |
| `tools/alpha.py` | Alpha因子 (Z-Score/Hurst/熵/量比等) | 想做深度统计分析 |
| `tools/entry_signal.py` | 入场信号聚合 (±100评分) | 想要综合评分和具体入场/止损/止盈价 |
| `tools/position_sizing.py` | 仓位计算 (固定风险/凯利/波动率调整) | 已确定入场价和止损价，要算买多少 |

所有分析工具统一调用格式：
```bash
python tools/<module>.py {SYMBOL} [--vs SPY]
```

仓位计算调用格式：
```bash
python tools/position_sizing.py {SYMBOL} {账户权益} {入场价} {止损价} [--risk 0.01] [--winrate 0.5] [--rr 2.0]
```

#### 工具选择指南

**你不需要每次运行所有工具。** 根据 Phase 1-3 收集到的信息，自主判断：

**情绪/价位获取（每个 symbol 必做）**：
```bash
python -c "from tools.calculate import format_sentiment_report, get_concrete_price; print(format_sentiment_report('{SYMBOL}')); print(get_concrete_price('{SYMBOL}'))"
```

**然后根据具体情况选择工具组合**，以下是典型场景参考（不是强制规则）：

| 场景 | 推荐组合 | 理由 |
|------|---------|------|
| 突发利多 + 想做多 | trend_structure → smart_money → entry_signal | 确认趋势支撑、资金跟进、然后拿入场价 |
| 突发利空 + 想做空 | market_psychology → votality_risk → entry_signal | 检查是否已超卖、波动率状态、然后拿入场价 |
| 油价飙升 + 能源股 | macro_lines → trend_structure → entry_signal | 看大趋势位置、确认突破、拿入场价 |
| 地缘冲突 + 高波动 | votality_risk → market_psychology → entry_signal | 先看波动率环境、再看情绪极值 |
| 方向不确定 | entry_signal（先跑综合评分决定方向） | 让评分体系告诉你方向 |
| 想深度挖掘 | alpha → 任意组合 | 统计因子发现隐藏信号 |

**关键判断原则**：
- 如果新闻催化剂非常强（如战争升级、重大政策），技术面权重降低，新闻权重升高
- 如果新闻方向和技术面矛盾，降低置信度，不要强行入场
- 背离信号（RSI/MFI/CCI）优先级最高，出现背离必须重视
- 波动率异常高时（ATR 远超均值），必须跑 votality_risk 确认止损距离

**入场信号确认后，计算仓位（ACTIONABLE 的 symbol 必做）**：

从 entry_signal 输出中提取入场价和止损价，然后：
```bash
# 基础仓位计算（默认1%风险）
python tools/position_sizing.py {SYMBOL} {账户权益} {入场价} {止损价}

# 高波动市场建议降低风险到0.5%
python tools/position_sizing.py {SYMBOL} {账户权益} {入场价} {止损价} --risk 0.005
```

将分析结果追加到报告：

```
== Phase 4: Quantitative Analysis ==

--- {SYMBOL} ---
News Direction: {LONG/SHORT}
Sentiment Score: {score}
Current Price: {price}

Tool Selection Rationale: {why these tools were chosen}

Technical Signals:
  - {tool_name}: {key finding}
  - ...

Entry Signal Score: {score}/100
Direction: {LONG/SHORT/NEUTRAL}
Entry: ${price} | Stop: ${price} | Target: ${price}

Position Sizing (if ACTIONABLE):
  Model: {fixed_risk/kelly/volatility_adjusted}
  Recommended Shares: {number}
  Risk Per Trade: ${amount} ({percent}% of account)
```

### Phase 5: 综合判断

汇总 Phase 1-4 所有信息，为每个 symbol 产出最终判断：

```
== Phase 5: Final Verdict ==

ACTIONABLE:
  {SYMBOL} | {LONG/SHORT} | Confidence: {HIGH/MED/LOW}
    Catalyst: {one-line summary of unpriced event}
    Entry: ${price} | Stop: ${price} | Target: ${price}
    News Score: {strong/moderate/weak}
    Quant Score: {entry_signal score}/100
    Risk: {key risk factor}

WATCH (not actionable yet):
  {SYMBOL} | {reason to watch, not act}

SKIP:
  {SYMBOL} | {reason to skip}
```

**判断标准**：

| 条件 | 判定 |
|------|------|
| 未定价催化剂 + entry_signal ≥ 40 + 方向一致 | ACTIONABLE (HIGH) |
| 未定价催化剂 + entry_signal 20~39 + 方向一致 | ACTIONABLE (MED) |
| 未定价催化剂 + entry_signal < 20 或方向矛盾 | WATCH |
| 已定价 或 无明确催化剂 | SKIP |

完成后关闭浏览器：
```bash
browser-use close
```

## 输出文件

所有内容写入单个文件：`analysis_log/{YYYYMMDD_HHMM}.txt`

文件结构：
1. Phase 1: Social Media Scan
2. Phase 2: Breaking News Verification
3. Phase 3: Data Sync (记录同步状态)
4. Phase 4: Quantitative Analysis
5. Phase 5: Final Verdict

## 注意事项

- browser-use 搜索时必须打开文章详情页，不能只看 Google 摘要
- 超短线只关注最近 12 小时的事件，更早的事件大概率已被定价
- 不要过度分析已经被市场充分消化的旧闻
- 量化分析结果如果与新闻方向矛盾，降低置信度而不是忽略矛盾
- 每个 Phase 完成后立即写入文件，不要等全部完成再写
