---
name: social-media-scraper
description: 社交媒体数据抓取工具。当用户想抓取、查看、获取推特/X平台上指定用户的最新推文时使用。触发词包括"推文"、"推特"、"tweet"、"X"、"抓取推文"、"社交媒体"、"KOL"、"大V"、"舆情"以及任何与X/Twitter用户动态相关的请求。
---

# 社交媒体数据抓取工具

抓取 X (Twitter) 平台上指定用户的最新推文。

## 功能

### 批量抓取用户推文

从 `x_user_id.json` 读取用户列表，抓取每人最近 24 小时内最多 20 条推文。

```bash
python tools/x_fetch_cli.py
```

无需传参，用户列表由项目根目录的 `x_user_id.json` 配置：

```json
[
  {"user_id": "44196397", "label": "elonmusk"},
  {"user_id": "123456789", "label": "some_other_user"}
]
```

## 输出格式

每条推文一行，包含用户名、时间、内容和互动指标：

```
[@elonmusk Wed Mar 12 08:30:00 +0000 2026] 推文正文内容 | views=1234 likes=567 rt=89
```

特殊推文追加标记：
- 转推：`[RETWEET of @原作者]: 原文内容`
- 引用：`[QUOTE of @原作者]: 原文内容`

推文结果输出到 stdout，进度日志输出到 stderr。

## 使用场景

- 抓取关注 KOL 的最新动态，用于舆情判断
- 配合量化分析工具，先获取社交媒体情绪再做技术面验证
- 管道输出：`python tools/x_fetch_cli.py > tweets.txt`
