---
name: social-media-scraper
description: 社交媒体数据抓取工具。当用户想抓取、查看、获取推特/X平台上指定用户的最新推文时使用。触发词包括"推文"、"推特"、"tweet"、"X"、"抓取推文"、"社交媒体"、"KOL"、"大V"、"舆情"以及任何与X/Twitter用户动态相关的请求。
---

# 社交媒体数据抓取工具

抓取 X (Twitter) 和 Reddit 的最新帖子。

## 使用方法

```bash
# 默认抓取最近 24 小时（1440 分钟）
python3 cli/social_media_cli.py

# 抓取最近 60 分钟
python3 cli/social_media_cli.py --minutes 60
```

## 数据源配置

### X (Twitter)

用户列表由项目根目录的 `x_user_id.json` 配置：

```json
[
  {"user_id": "44196397", "label": "elonmusk"}
]
```

### Reddit

Subreddit 列表由项目根目录的 `subreddits.json` 配置：

```json
[
  {"subreddit": "wallstreetbets", "label": "WSB"},
  {"subreddit": "stocks", "label": "Stocks"}
]
```

## 输出格式

### X 推文

```
[@elonmusk Wed Mar 12 08:30:00 +0000 2026] 推文内容 | views=1234 likes=567 rt=89
```

### Reddit 帖子

```
[r/wallstreetbets 2026-03-21 08:30:00 UTC u/someone] 标题 | score=123 comments=45
```

结果输出到 stdout，进度日志输出到 stderr。
