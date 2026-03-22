---
name: stock-data
description: 股票数据工具。当用户想同步、拉取、更新、获取、查询股票日线或分钟线数据时使用。触发词包括"抓取"、"拉取"、"同步"、"日线"、"分钟线"、"K线数据"、"股价数据"、"dayline"、"intraday"、"sync"、"数据更新"、"获取数据"、"查询数据"以及任何与股票历史行情数据获取相关的请求。
---

# 股票数据工具

从 Yahoo Finance 同步股票日线和分钟线数据，支持同步后直接查询并以 JSON 返回。

## CLI 调用方式

```bash
python cli/stock_data.py <command> [SYMBOLS...] [OPTIONS]
```

## 子命令

### 1. sync — 纯同步数据

同步股票数据到本地数据库，不返回查询结果。

```bash
# 同步指定股票的日线和分钟线
python cli/stock_data.py sync AAPL TSLA NVDA

# 只同步日线
python cli/stock_data.py sync AAPL TSLA --daily-only

# 只同步分钟线
python cli/stock_data.py sync NVDA --intraday-only

# 同步全部成分股日线（需用户明确要求）
python cli/stock_data.py sync --daily-only

# 只同步 NASDAQ100 成分股
python cli/stock_data.py sync --daily-only --index nasdaq100
```

| 参数 | 说明 |
|------|------|
| `SYMBOLS` | 位置参数，一个或多个股票代码。省略则从 IndexStock 表读取 |
| `--daily-only` | 只同步日线 |
| `--intraday-only` | 只同步分钟线 |
| `--index` | 指定指数筛选：`all`（默认）、`sp500`、`nasdaq100` |
| `--limit N` | 限制 ticker 数量 |
| `--sleep S` | ticker 间等待秒数（默认 0.2） |

### 2. daily — 获取日线数据

同步日线后查询最近 N 个交易日的数据，输出 JSON。

```bash
# 获取 AAPL 最近5个交易日的日线（默认）
python cli/stock_data.py daily AAPL

# 获取多只股票最近10个交易日的日线
python cli/stock_data.py daily AAPL TSLA NVDA --days 10
```

| 参数 | 说明 |
|------|------|
| `SYMBOLS` | 必填，一个或多个股票代码 |
| `--days N` | 返回的交易日数（默认 5） |

### 3. minute — 获取分钟线数据

同步分钟线后查询最近 N 分钟的数据，输出 JSON。

```bash
# 获取 AAPL 最近60分钟的分钟线（默认）
python cli/stock_data.py minute AAPL

# 获取多只股票最近120分钟的分钟线
python cli/stock_data.py minute AAPL TSLA --minutes 120
```

| 参数 | 说明 |
|------|------|
| `SYMBOLS` | 必填，一个或多个股票代码 |
| `--minutes N` | 回溯分钟数（默认 60） |

## JSON 输出格式

daily 和 minute 子命令输出 JSON，按 symbol 分组：

```json
{
  "AAPL": [
    {"ts": 1711065600, "trade_day": "20260320", "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.5, "volume": 1234567},
    ...
  ],
  "TSLA": [...]
}
```

minute 子命令额外包含 `interval` 字段（如 `"1m"`、`"5m"`）。

## 注意事项

- 分钟线受 Yahoo 限制，1m 粒度只能拉最近 8 天，代码内部会自动 fallback 到更大粒度
- `BF.B`、`BRK.B` 等含 `.` 的 ticker 可能被 yfinance 误判为退市，属正常警告
- 首次批量同步前需确保 IndexStock 表有数据，否则先执行 `python cli/update_index_stocks.py`

## 使用场景

- 获取特定股票的最新日线/分钟线数据（JSON 格式）
- 配合 quant-analysis skill 使用，先获取数据再做技术分析
- 每日定时更新全量行情数据
