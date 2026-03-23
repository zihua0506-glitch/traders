---
name: swing-scout
description: 超短线股票机会扫描工具。当用户想进行超短线交易分析、扫描突发新闻驱动的交易机会、或要求完整的"社交媒体+新闻+量化"综合分析时使用。触发词包括"超短线分析"、"扫描机会"、"swing scout"、"今日机会"、"开盘分析"、"盘前分析"、"突发新闻分析"以及任何需要结合舆情和量化的超短线交易分析请求。
---

# 超短线机会扫描工具 (Swing Scout)

基于"**突发新闻驱动 + 量化验证**"的超短线分析流水线。聚焦纳斯达克100和标普500成分股中，受突发事件影响、尚未被市场完全定价的交易机会。

## 核心原则

- **只关注超短线**：自上一个交易日收盘（美东 4pm）以来的突发新闻，不做长线推演
- **只关注未定价事件**：盘后/周末/节假日发生的、下一个交易日开盘才会反映的事件
- **社媒发现，新闻验证，量化确认**：先用社媒找到线索，再用新闻确认催化剂，最后用量化决定交易结构
- **最终结论由 LLM 综合裁决**：Phase 5 必须显式综合社媒、新闻、量化三类结果，不能只机械跟随单一分数
- **只看纳指100和标普500成分股**：Phase 1 提取的 symbol 必须属于这两个指数，非成分股标记为 SKIP
- **结果全部落盘**：所有分析写入 `analysis_log/{YYYYMMDD_HHMM}.txt`

## 执行流程

### Phase 0: Preflight 检查

在开始之前，做最小必要检查：

```bash
# 确保 analysis_log 目录存在
mkdir -p analysis_log

# 确认当前时间和上一个交易日收盘时间
# 工作日：当天 4pm ET 之前 → 上一个交易日收盘 = 前一个工作日 4pm ET
# 工作日：当天 4pm ET 之后 → 上一个交易日收盘 = 当天 4pm ET
# 周末（周六/周日）→ 上一个交易日收盘 = 上周五 4pm ET
# 美股假日 → 上一个交易日收盘 = 假日前最后一个交易日 4pm ET
```

确定 `LAST_CLOSE`（上一个交易日收盘时间），后续所有 Phase 以此为基准判断事件是否"未定价"。

Preflight 不做复杂恢复或额外探测。只要发现工具、配置、数据源、网络等问题，记录到报告里并结束；不要把环境问题误写成交易结论。

**提前退出条件**：
- 如果社交媒体抓取返回空结果，记录原因并结束
- 如果 Phase 2 没有发现任何未定价事件，记录原因并结束（不需要跑 Phase 3-5）

### Phase 1: 社交媒体舆情采集

调用 social-media-scraper 抓取最新社交媒体数据：

```bash
python3 cli/social_media_cli.py --minutes 1440
```

分析输出，提取：

1. **关注列表**：哪些股票 symbol 被提及或受影响（**必须是纳指100或标普500成分股**，非成分股直接丢弃）
2. **关注原因**：每个 symbol 为什么值得关注（用一句话概括）
3. **情绪方向**：社交媒体对该 symbol 的情绪倾向（利多/利空/争议）
4. **搜索计划**：后续需要在网上验证的关键问题列表

如果没有提取到任何候选 symbol，记录原因并结束流程。

将以上内容写入 `analysis_log/{YYYYMMDD_HHMM}.txt`，格式：

```
=== SWING SCOUT REPORT ===
Date: {date}
Generated Local: {YYYY-MM-DD HH:MM TZ}
Generated ET: {YYYY-MM-DD HH:MM ET}
LAST_CLOSE_ET: {YYYY-MM-DD HH:MM ET}
LAST_CLOSE_UNIX: {unix_ts}
Social Data Source: cli/social_media_cli.py --minutes 1440
News Verification Source: browser-use manual article verification
Price Data Source: sentiment.db.stock_price_bars

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
- Google 搜索时间范围根据 Phase 0 确定的 `LAST_CLOSE` 动态调整：工作日盘后用 `tbs=qdr:h6`，周末/假期用 `tbs=qdr:d3`（覆盖整个休市期间）
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
  Source URL: {url}
  Source Type: {article/liveblog/company-post/search-snippet}
  Published At ET: {YYYY-MM-DD HH:MM ET if known, else unknown}
  Event Time ET: {YYYY-MM-DD HH:MM ET if known, else estimated window}
  Impact: {symbol} {direction} - {why}

[ALREADY PRICED] Event description
  Source URL: {url}
  Source Type: {article/liveblog/company-post/search-snippet}
  Published At ET: {YYYY-MM-DD HH:MM ET if known, else unknown}
  Event Time ET: {YYYY-MM-DD HH:MM ET if known, else estimated window}
  Reason: happened during market hours / already reflected in Friday close

Final Watch List (unpriced events only):
  SYMBOL | DIRECTION | CATALYST | NEWS_EVIDENCE (strong/moderate/weak)
```

如果没有发现任何未定价事件，记录原因并结束流程（不需要跑 Phase 3-5）。

### Phase 3: 数据获取

基于 Phase 2 的 Final Watch List 中的 symbol，调用 stock-data 获取日线和分钟线数据。

**注意**：`stock_data.py` 会先打印 sync 进度日志，然后输出 JSON 数据，不是纯 JSON。

```bash
# 获取最近10个交易日的日线数据
python3 cli/stock_data.py daily {SYMBOLS} --days 10

# 获取最近60分钟的分钟线数据
python3 cli/stock_data.py minute {SYMBOLS} --minutes 60
```

同时拉取对应的基准指数：
- 如果关注个股多为科技股，加 QQQ
- 如果关注能源/国防股，加 SPY XLE

**错误处理**：如果某个 symbol 同步失败（网络问题、ticker 不存在等），记录失败原因，跳过该 symbol 的 Phase 4 分析。

将同步状态追加到报告：

```
== Phase 3: Data Sync ==

Synced: {SYMBOL1}, {SYMBOL2}, ...
Failed: {SYMBOL3} (reason: ...)
Benchmark: {QQQ/SPY/XLE}
Price DB Table: stock_price_bars

Snapshot Metadata:
  SYMBOL | LATEST_BAR_ET | INTERVAL | DATA_SOURCE
```

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

调用格式（注意各工具参数不同）：
```bash
# 分析工具（支持 --vs 对比）
python3 tools/smart_money.py {SYMBOL} [--vs SPY]
python3 tools/trend_structure.py {SYMBOL} [--vs SPY]
python3 tools/market_psychology.py {SYMBOL} [--vs QQQ]
python3 tools/votality_risk.py {SYMBOL} [--vs SPY]
python3 tools/macro_lines.py {SYMBOL} [--vs SPY]
python3 tools/alpha.py {SYMBOL} [--vs INTC]

# 入场信号（无 --vs 参数）
python3 tools/entry_signal.py {SYMBOL}

# 仓位计算（需要入场价和止损价）
python3 tools/position_sizing.py {SYMBOL} {账户权益} {入场价} {止损价} [--risk 0.01] [--winrate 0.5] [--rr 2.0]
```

#### 工具选择指南

**你不需要每次运行所有工具。** 根据 Phase 1-3 收集到的信息，自主判断：

**情绪/价位获取（每个 symbol 必做）**：
```bash
python3 -c "from tools.calculate import format_sentiment_report, get_concrete_price; print(format_sentiment_report('{SYMBOL}')); print(get_concrete_price('{SYMBOL}'))"
```
如需在 Phase 4 / Phase 5 写入明确的社媒分数，可额外调用：
```bash
python3 -c "from tools.calculate import load_sentiment; print(load_sentiment('{SYMBOL}', 24))"
```
至少提取并记录以下社媒字段：
- `weighted_score`
- `sentiment_label`
- `total`（样本量）
- `top_summaries`（关键观点，可简写 1-2 条）

如果情绪或价位数据返回空/报错，记录失败原因；情绪数据为空时不必立刻 SKIP，可以继续做新闻和量化分析，但必须在 Phase 5 明确标注 `Social Score: unavailable` 并降低置信度。

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

**入场/止损价选择规则**：

entry_signal 会输出多种入场策略和止损方法，按以下优先级选择：
- **入场价**：优先使用 entry_signal 推荐的最优入场策略；如果评分 ≥ 65 且趋势市，用市价入场；否则用回踩入场
- **止损价**：优先使用结构止损（SuperTrend + 摆动极值），因为最符合市场逻辑；高波动时改用 ATR 止损
- **止盈目标**：根据 entry_signal 输出的市场状态（趋势/震荡/过渡）选择对应的 R/R 目标

**入场信号确认后，计算仓位（ACTIONABLE 的 symbol 必做）**：

从 entry_signal 输出中按上述规则提取入场价和止损价，然后：
```bash
# 基础仓位计算（默认1%风险）
python3 tools/position_sizing.py {SYMBOL} {账户权益} {入场价} {止损价}

# 高波动市场建议降低风险到0.5%
python3 tools/position_sizing.py {SYMBOL} {账户权益} {入场价} {止损价} --risk 0.005
```

**账户权益未知时**：跳过 position_sizing，在报告中注明"账户权益未提供，仓位计算跳过"，其余分析照常进行。

将分析结果追加到报告：

```
== Phase 4: Quantitative Analysis ==

--- {SYMBOL} ---
News Direction: {LONG/SHORT}
Social Score: {weighted_score:+.2f} ({sentiment_label}, n={total})
Current Price: {price}
Price Timestamp ET: {YYYY-MM-DD HH:MM ET}
Price Interval: {1m/5m/15m/30m/60m/1d}
Price Source: sentiment.db.stock_price_bars

Tool Selection Rationale: {why these tools were chosen}

Technical Signals:
  - {tool_name}: {key finding}
  - ...

Entry Signal Score: {score}/100
Direction: {LONG/SHORT/WAIT}
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
    Social Score: {weighted_score:+.2f} ({sentiment_label}, n={total}) / unavailable
    Data As Of ET: {YYYY-MM-DD HH:MM ET}
    Price Source: sentiment.db.stock_price_bars ({interval})
    Entry: ${price} | Stop: ${price} | Target: ${price}
    News Score: {strong/moderate/weak}
    Quant Score: {entry_signal score}/100
    Why It Is Actionable: {how social + news + quant combine into one trade thesis}
    Risk: {key risk factor}

WATCH (not actionable yet):
  {SYMBOL} | {reason to watch, not act}
    Social Score: {weighted_score:+.2f} ({sentiment_label}, n={total}) / unavailable
    News Score: {strong/moderate/weak}
    Quant Score: {entry_signal score}/100
    Data As Of ET: {YYYY-MM-DD HH:MM ET}
    Price Source: sentiment.db.stock_price_bars ({interval})

SKIP:
  {SYMBOL} | {reason to skip}
    Social Score: {weighted_score:+.2f} ({sentiment_label}, n={total}) / unavailable
    News Score: {strong/moderate/weak / none}
    Quant Score: {entry_signal score}/100 / unavailable
    Data As Of ET: {YYYY-MM-DD HH:MM ET if available}
    Price Source: {sentiment.db.stock_price_bars ({interval}) / none}
```

**判断标准**：

Phase 5 由 LLM 做综合分析，不要机械套用 `entry_signal` 阈值表。

`entry_signal` 的作用：
- 它是 **量化侧的重要锚点**，用来衡量技术面方向、结构完整度、入场/止损/止盈质量
- 它 **不是唯一裁决器**，不能压过所有社媒和新闻信息
- 当它与新闻/社媒冲突时，重点不是“谁覆盖谁”，而是说明冲突来自哪里、哪个维度更可信、为什么

综合判断时，至少同时回答下面 4 个问题：
1. **社媒是否在放大/提前反映这个事件？** 看 `Social Score`、样本量、关键观点是否一致
2. **新闻催化剂是否真实、具体、且未被定价？** 看事件时间、影响路径、主流媒体确认强度
3. **量化结构是否支持立刻交易，而不是只支持“方向上可能对”？** 看 `Quant Score`、市场状态、入场/止损是否合理
4. **三者冲突时，哪个维度最应该主导？** 必须写清理由，不能只给结论

建议的综合裁决思路：
- **社媒 + 新闻 + 量化同向**：优先考虑 `ACTIONABLE`
- **新闻很强，但量化滞后或冲突**：可以给 `WATCH`，也可以给低置信度 `ACTIONABLE`，但必须解释为什么新闻权重更高，以及怎么控制 gap risk
- **量化很强，但新闻弱/已定价，社媒也不支持**：更倾向 `WATCH` 或 `SKIP`，避免把纯技术反弹误判成事件交易
- **社媒很热但新闻证据弱**：通常不应直接 `ACTIONABLE`，除非你明确说明这是“情绪驱动交易”而不是“新闻驱动交易”
- **任一关键维度缺失**：允许继续输出结论，但必须显式标注缺口并下调置信度

如果最终结论与 `entry_signal` 方向不同，或在 `entry_signal = WAIT` 时仍给出 `ACTIONABLE`，必须额外写一句：
- `Override Reason: {why LLM overrode the raw quant direction}`

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
- 超短线只关注 `LAST_CLOSE` 之后的事件，更早的事件大概率已被定价
- 不要过度分析已经被市场充分消化的旧闻
- 量化分析结果如果与新闻方向矛盾，降低置信度而不是忽略矛盾
- 每个 Phase 完成后立即写入文件，不要等全部完成再写
- 所有时间统一优先写 ET（美东时间）；如果原文只有相对时间，明确标注 `estimated`
- 所有价格都要带 `Price Timestamp ET`、`Price Interval`、`Price Source`
- 除非数据源明确标注盘前/盘后，否则不要主观写 `pre-market` / `after-hours`，统一写成“latest DB bar”
