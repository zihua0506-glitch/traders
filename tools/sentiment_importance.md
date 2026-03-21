# 情绪数据重要性评分体系

> 目标: 从噪音中筛选真正影响价格的舆情信号，给每条帖子打出 `[0, 1]` 的重要性分，
> 供聚合分析时作为权重使用，替代现有的仅用 `likes + 1` 粗暴加权的方案。

---

## 一、评分维度总览

| 维度 | 符号 | 范围 | 核心问题 |
|------|------|------|---------|
| 时效性衰减 | T | [0, 1] | 这条信息还"新鲜"吗？ |
| 来源可信度 | S | [0, 1] | 这个平台/类型的信号质量如何？ |
| 互动热度   | E | [0, 1] | 市场对这条信息的关注度有多高？ |
| 相关性     | R | [0, 1] | 这条信息和目标标的有多直接的关系？ |
| 情绪置信度 | C | [0, 1] | FinBERT 对这条信息的情绪判断有多确定？ |

---

## 二、各维度计算公式

### 1. 时效性衰减 T — 指数半衰期模型

情绪信息的影响力随时间指数衰减，半衰期设为 **4 小时**（日内交易窗口）。

```
age_hours = (now_ts - post_time) / 3600

T = exp( -ln(2) / half_life × age_hours )
  = exp( -0.1733 × age_hours )
```

| 发布距今 | T 值 |
|---------|------|
| 0 小时  | 1.00 |
| 2 小时  | 0.71 |
| 4 小时  | 0.50 |
| 8 小时  | 0.25 |
| 24 小时 | 0.06 |

> **参数调整建议**: 日线交易者可将 half_life 改为 24h；宏观分析可用 72h。

---

### 2. 来源可信度 S — 平台基础权重 × 内容类型修正

#### 2.1 平台基础权重

```python
SOURCE_BASE = {
    'x':          0.90,  # KOL 推文，原始一手信息，传播快
    'finviz':     0.85,  # 专业财经媒体，经过编辑筛选
    'yahoo':      0.80,  # 主流财经新闻，可信但滞后
    'reddit':     0.70,  # 社区讨论，散户情绪聚集地
    'stocktwits': 0.65,  # 纯散户打分，噪音较多
}
S_base = SOURCE_BASE.get(source, 0.60)
```

#### 2.2 内容类型修正

转推是二手信息，回复是碎片讨论，均需降权：

```
S = S_base
    × (0.50 if is_retweet else 1.0)   # 转推降至一半
    × (0.75 if is_reply   else 1.0)   # 回复讨论串降权
```

> **逻辑**: 原创内容 > 引用转发 > 转推 > 回复，原创者才是信息源头。

---

### 3. 互动热度 E — 加权对数归一化

不同互动行为的信号价值不同：

| 字段       | 权重 | 理由 |
|-----------|------|------|
| shares    | ×2.0 | 主动传播，认可度最强 |
| comments  | ×1.5 | 引发讨论，争议或热点 |
| likes     | ×1.0 | 基础认可 |
| bookmarks | ×1.0 | 认为重要，私下收藏 |
| views     | ×0.05| 曝光量，被动指标 |

```
raw_engagement = 2.0×shares + 1.5×comments + 1.0×likes + 1.0×bookmarks + 0.05×views

REFERENCE_CAP = 10_000  # 超过此互动量视为顶级，上限截断

E = log10(min(raw_engagement, REFERENCE_CAP) + 1) / log10(REFERENCE_CAP + 1)
```

| raw_engagement | E 值（参考万级上限） |
|---------------|-------------------|
| 0             | 0.00 |
| 10            | 0.25 |
| 100           | 0.50 |
| 1,000         | 0.75 |
| 10,000+       | 1.00 |

---

### 4. 相关性 R — 目标标的匹配度

评估这条帖子与目标标的的针对性，越直接越高：

```python
target = symbol.upper().split('-')[0]  # BTC-USD → BTC

if target in tickers:                       # tickers JSON 精确命中
    R = 1.00
elif target in content.upper():            # 正文包含代码
    R = 0.80
elif any(kw in content.upper()             # 行业关键词（需预定义）
         for kw in SECTOR_KEYWORDS.get(target, [])):
    R = 0.40
else:                                      # 泛市场讨论
    R = 0.20
```

**SECTOR_KEYWORDS 示例**:
```python
SECTOR_KEYWORDS = {
    'NVDA': ['GPU', 'AI', 'CUDA', 'JENSEN', 'NVIDIA', 'DATACENTER'],
    'BTC':  ['BITCOIN', 'CRYPTO', 'HALVING', 'SATOSHI', 'LIGHTNING'],
    'TSLA': ['TESLA', 'ELON', 'EV', 'GIGAFACTORY', 'CYBERTRUCK'],
}
```

---

### 5. 情绪置信度 C — FinBERT 打分绝对值

FinBERT summary 格式为 `"FinBERT: positive | score=+0.923"`，从中提取分值：

```python
import re

match = re.search(r'score=([+-]?\d+\.?\d*)', summary)
score = float(match.group(1)) if match else 0.0

C = abs(score)
```

| |sentiment_score| | C 值 | 含义 |
|-----------------|------|------|
| > 0.80          | 高   | 强烈情绪，高置信 |
| 0.50 ~ 0.80     | 中   | 有倾向，但不确定 |
| 0.10 ~ 0.50     | 低   | 弱信号 |
| < 0.10          | 极低 | 接近中性，信息量少 |

> **注意**: 纯中性帖子 (`C ≈ 0`) 不代表没有价值，应保留但权重最低。

---

## 三、综合评分公式

采用 **「门控 × 信号质量」** 的乘法架构：

- **T × S**: 门控层，时效性和来源可信度同时作为衰减因子
- **E / R / C**: 信号质量层，加权求和

```
Importance = T × S × (w_E × E + w_R × R + w_C × C)
```

### 推荐权重

| 权重 | 值   | 理由 |
|------|------|------|
| w_E  | 0.35 | 互动是市场关注度的直接体现 |
| w_R  | 0.40 | 直接针对标的比泛市场讨论价值高得多 |
| w_C  | 0.25 | FinBERT 置信度是情绪强度的客观量化 |

```python
def importance_score(
    post_time, source, is_retweet, is_reply,
    shares, comments, likes, bookmarks, views,
    tickers, content, summary,
    target_symbol,
    half_life_hours=4,
    w_E=0.35, w_R=0.40, w_C=0.25,
) -> float:

    import math, re, time

    # --- T: 时效性 ---
    age_h = (time.time() - post_time) / 3600
    T = math.exp(-math.log(2) / half_life_hours * age_h)

    # --- S: 来源可信度 ---
    SOURCE_BASE = {'x': 0.90, 'finviz': 0.85, 'yahoo': 0.80,
                   'reddit': 0.70, 'stocktwits': 0.65}
    S = SOURCE_BASE.get(source, 0.60)
    if is_retweet: S *= 0.50
    if is_reply:   S *= 0.75

    # --- E: 互动热度 ---
    raw = 2.0*shares + 1.5*comments + 1.0*likes + 1.0*bookmarks + 0.05*views
    REF = 10_000
    E = math.log10(min(raw, REF) + 1) / math.log10(REF + 1)

    # --- R: 相关性 ---
    target = target_symbol.upper().split('-')[0]
    if target in (tickers or []):
        R = 1.00
    elif target in (content or '').upper():
        R = 0.80
    else:
        R = 0.20

    # --- C: 情绪置信度 ---
    m = re.search(r'score=([+-]?\d+\.?\d*)', summary or '')
    C = abs(float(m.group(1))) if m else 0.0

    return T * S * (w_E * E + w_R * R + w_C * C)
```

---

## 四、分级阈值与使用建议

| 分数区间  | 等级 | 聚合权重倍数 | 处理建议 |
|----------|------|------------|---------|
| ≥ 0.70   | 🔴 高 | ×3.0       | 立即纳入分析，触发预警检查 |
| 0.40~0.70| 🟡 中 | ×1.0       | 正常纳入情绪聚合 |
| 0.20~0.40| 🟢 低 | ×0.5       | 降权纳入，噪音参考 |
| < 0.20   | ⚪ 噪音| ×0         | 过滤，不参与聚合计算 |

### 在聚合中的使用方式

```python
# 替换现有的 weights = [likes + 1] 方案
weights = [importance_score(...) for post in posts]

# 加权情绪得分
weighted_sentiment = sum(
    score * w for score, w in zip(sentiment_scores, weights)
) / (sum(weights) + 1e-8)
```

---

## 五、典型案例对比

| 场景 | T | S | E | R | C | 综合分 |
|------|---|---|---|---|---|--------|
| Elon 发推提 BTC，100k 转发，刚发 | 1.00 | 0.90 | 0.97 | 1.00 | 0.95 | **0.88** |
| Reddit 帖子讨论 BTC，50 赞，6h 前 | 0.35 | 0.70 | 0.30 | 0.80 | 0.70 | **0.21** |
| 转推某 Finviz 新闻，无互动，12h 前 | 0.13 | 0.43 | 0.00 | 0.20 | 0.50 | **0.02** |
| 高互动 Reddit 讨论，不含目标标的 | 0.80 | 0.70 | 0.85 | 0.20 | 0.60 | **0.18** |

> 案例 4 说明: 即使互动很高，**相关性低是最大的降分因子**，符合"噪音也可以很热"的现实。

---

## 六、参数调优建议

| 场景 | 调整方向 |
|------|---------|
| 加密货币 24h 市场 | half_life 缩短至 **2h** |
| A股日线交易者 | half_life 扩大至 **24h** |
| 重视 KOL 推文 | 提高 `x` 的 SOURCE_BASE 至 **0.95** |
| 重视散户情绪共振 | 提高 w_E 至 **0.50**，降低 w_R 至 **0.25** |
| FinBERT 数据不足 | 固定 C = 0.5，去掉 w_C 这一项 |
