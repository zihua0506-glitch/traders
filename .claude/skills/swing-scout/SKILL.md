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

### Phase 4: 量化分析

对 Phase 2 筛选出的每个 symbol，执行量化验证：

**Step 4a: 获取情绪和价位**

```bash
python -c "from tools.calculate import format_sentiment_report, get_concrete_price; print(format_sentiment_report('{SYMBOL}')); print(get_concrete_price('{SYMBOL}'))"
```

**Step 4b: 根据新闻方向选择分析工具**

| 新闻方向 | 必调工具 | 目的 |
|---------|---------|------|
| 利多（做多） | trend_structure + smart_money | 确认趋势支撑 + 资金是否跟进 |
| 利空（做空） | market_psychology + votality_risk | 检查是否已超卖 + 波动率状态 |
| 不确定 | entry_signal（综合评分） | 让评分体系决定方向 |

```bash
# 示例：利多方向
python tools/trend_structure.py {SYMBOL} --vs SPY
python tools/smart_money.py {SYMBOL}

# 示例：利空方向
python tools/market_psychology.py {SYMBOL}
python tools/votality_risk.py {SYMBOL}
```

**Step 4c: 入场信号**

对置信度较高的 symbol 执行：

```bash
python tools/entry_signal.py {SYMBOL}
```

将分析结果追加到报告：

```
== Phase 4: Quantitative Analysis ==

--- {SYMBOL} ---
News Direction: {LONG/SHORT}
Sentiment Score: {score}
Current Price: {price}

Technical Signals:
  - {tool_name}: {key finding}
  - ...

Entry Signal Score: {score}/100
Direction: {LONG/SHORT/NEUTRAL}
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
