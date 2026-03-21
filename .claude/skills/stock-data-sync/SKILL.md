---
name: stock-data-sync
description: 股票数据抓取工具。当用户想同步、拉取、更新股票日线或分钟线数据时使用。触发词包括"抓取"、"拉取"、"同步"、"日线"、"分钟线"、"K线数据"、"股价数据"、"dayline"、"intraday"、"sync"、"数据更新"以及任何与股票历史行情数据获取相关的请求。
---

# 股票数据抓取工具

从 Yahoo Finance 同步股票日线和分钟线数据，存入本地数据库。

## CLI 调用方式

```bash
python cli/sync_daily_bars.py [SYMBOLS...] [OPTIONS]
```

**必须指定股票代码**，除非用户明确要求同步全部成分股。

### 使用示例

```bash
# 同步指定股票的日线和分钟线
python cli/sync_daily_bars.py AAPL TSLA NVDA

# 同步指定股票的日线
python cli/sync_daily_bars.py AAPL TSLA --daily-only

# 同步指定股票的分钟线
python cli/sync_daily_bars.py NVDA --intraday-only

# 同步全部成分股日线（需用户明确要求）
python cli/sync_daily_bars.py --daily-only

# 只同步 NASDAQ100 成分股
python cli/sync_daily_bars.py --daily-only --index nasdaq100
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `SYMBOLS` | 位置参数，一个或多个股票代码（如 AAPL TSLA）。省略则从 IndexStock 表读取 |
| `--daily-only` | 只同步日线 |
| `--intraday-only` | 只同步分钟线 |
| `--index` | 指定指数筛选：`all`（默认）、`sp500`、`nasdaq100`，仅在未指定 SYMBOLS 时生效 |
| `--limit N` | 限制 ticker 数量，0 表示全部 |
| `--sleep S` | 每个 ticker 之间的等待秒数（默认 0.2） |

## 注意事项

- 分钟线受 Yahoo 限制，1m 粒度只能拉最近 8 天，代码内部会自动 fallback 到更大粒度
- `BF.B`、`BRK.B` 等含 `.` 的 ticker 可能被 yfinance 误判为退市，属正常警告
- 首次批量同步前需确保 IndexStock 表有数据，否则先执行 `python cli/update_index_stocks.py`

## 使用场景

- 抓取特定股票的最新日线/分钟线数据
- 每日定时更新全量行情数据
- 配合 quant-analysis skill 使用，先同步数据再做技术分析
