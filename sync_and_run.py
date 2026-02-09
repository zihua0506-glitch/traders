"""完整的数据同步和情绪分析流程

1. 同步 target.txt 中所有符号的价格数据（1年天级 + 24小时15分钟）
2. 运行 main.py 收集情绪数据（24小时）
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

from collectors.yahoo import sync_stock_price_bars
from models import StockPriceBar, IndexStock


def load_target_symbols() -> List[str]:
    """从 target.txt 加载目标符号"""
    target_file = Path("target.txt")
    if not target_file.exists():
        print("错误: target.txt 文件不存在")
        sys.exit(1)

    symbols = []
    with open(target_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#") or line.startswith("Predict"):
                continue

            # 提取符号（例如 "BTC" 或 "SP500 (index)"）
            symbol = line.split("(")[0].strip()
            if symbol and not symbol.startswith("Iteration") and not symbol.startswith("Zihua") \
               and not symbol.startswith("John") and not symbol.startswith("Ruoting") \
               and not symbol.startswith("Market") and not symbol.endswith(":") \
               and not symbol.endswith("window:"):
                symbols.append(symbol)

    return symbols


def map_symbol_to_yahoo(symbol: str) -> str:
    """将符号映射到 Yahoo Finance 格式"""
    mapping = {
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
        "TESLA": "TSLA",
        "NVDIA": "NVDA",  # 用户拼写为 NVDIA
        "META": "META",
        "SP500": "^GSPC",  # S&P 500 指数
        "NV100": "^NDX",   # Nasdaq 100 指数
    }
    return mapping.get(symbol, symbol)


def sync_symbol_data(symbol: str, verbose: bool = True) -> Dict[str, Any]:
    """同步单个符号的价格数据

    - 天级数据：1年（用于计算 MA200, MA50 等）
    - 15分钟数据：24小时（用于短期分析）
    """
    yahoo_symbol = map_symbol_to_yahoo(symbol)

    if verbose:
        print(f"\n{'='*60}")
        print(f"同步 {symbol} ({yahoo_symbol})")
        print(f"{'='*60}")

    try:
        result = sync_stock_price_bars(
            yahoo_symbol,
            sync_daily=True,           # 同步天级数据（1年+）
            sync_intraday=True,        # 同步15分钟数据（24小时）
            daily_overlap_days=7,      # 重叠7天确保数据完整
            intraday_overlap_minutes=30,  # 重叠30分钟确保数据完整
        )

        if verbose:
            # 显示天级数据结果
            if "daily" in result:
                daily = result["daily"]
                print(f"\n天级数据 (1d):")
                print(f"  原始行数: {daily.get('raw_rows', 0)}")
                print(f"  获取行数: {daily.get('fetched_rows', 0)}")
                print(f"  插入: {daily.get('inserted', 0)}")
                print(f"  更新: {daily.get('updated', 0)}")
                print(f"  未变化: {daily.get('unchanged', 0)}")
                if daily.get('start_ts') and daily.get('end_ts'):
                    start_date = datetime.fromtimestamp(daily['start_ts']).strftime('%Y-%m-%d')
                    end_date = datetime.fromtimestamp(daily['end_ts']).strftime('%Y-%m-%d')
                    print(f"  时间范围: {start_date} 至 {end_date}")

            # 显示15分钟数据结果
            if "intraday" in result:
                intraday = result["intraday"]
                print(f"\n15分钟数据 ({intraday.get('interval', 'N/A')}):")
                print(f"  原始行数: {intraday.get('raw_rows', 0)}")
                print(f"  获取行数: {intraday.get('fetched_rows', 0)}")
                print(f"  插入: {intraday.get('inserted', 0)}")
                print(f"  更新: {intraday.get('updated', 0)}")
                print(f"  未变化: {intraday.get('unchanged', 0)}")
                if intraday.get('start_ts') and intraday.get('end_ts'):
                    start_time = datetime.fromtimestamp(intraday['start_ts']).strftime('%Y-%m-%d %H:%M')
                    end_time = datetime.fromtimestamp(intraday['end_ts']).strftime('%Y-%m-%d %H:%M')
                    print(f"  时间范围: {start_time} 至 {end_time}")

                if intraday.get('error'):
                    print(f"  [!] 错误: {intraday['error']}")

        return result

    except Exception as e:
        print(f"[!] 同步 {symbol} 失败: {e}")
        import traceback
        traceback.print_exc()
        return {"symbol": symbol, "error": str(e)}


def show_database_stats():
    """显示数据库统计信息"""
    print(f"\n{'='*60}")
    print("数据库统计")
    print(f"{'='*60}")

    try:
        total_bars = StockPriceBar.select().count()
        print(f"总 K 线数据: {total_bars:,} 条")

        # 按符号统计
        symbols = StockPriceBar.select(StockPriceBar.symbol).distinct()
        for symbol_row in symbols:
            symbol = symbol_row.symbol
            count = StockPriceBar.select().where(StockPriceBar.symbol == symbol).count()
            print(f"  {symbol}: {count:,} 条")

        # 按区间统计
        print("\n按区间统计:")
        intervals = ["1d", "15m", "5m", "1h"]
        for interval in intervals:
            count = StockPriceBar.select().where(StockPriceBar.interval == interval).count()
            if count > 0:
                print(f"  {interval}: {count:,} 条")

    except Exception as e:
        print(f"[!] 获取统计信息失败: {e}")


def main():
    """主函数"""
    print("="*60)
    print("LLM Trader - 数据同步和情绪分析")
    print("="*60)
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 步骤 1: 加载目标符号
    print("\n步骤 1: 加载目标符号...")
    symbols = load_target_symbols()
    print(f"找到 {len(symbols)} 个目标符号: {', '.join(symbols)}")

    # 步骤 2: 同步价格数据
    print("\n步骤 2: 同步价格数据到 sentiment.db...")
    start_time = time.time()

    results = {}
    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] 处理 {symbol}...")
        results[symbol] = sync_symbol_data(symbol, verbose=True)
        time.sleep(0.5)  # 避免请求过快

    elapsed = time.time() - start_time
    print(f"\n数据同步完成，耗时: {elapsed:.1f} 秒")

    # 显示数据库统计
    show_database_stats()

    # 步骤 3: 总结
    print(f"\n{'='*60}")
    print("同步总结")
    print(f"{'='*60}")

    success_count = 0
    for symbol, result in results.items():
        yahoo_symbol = map_symbol_to_yahoo(symbol)

        daily_ok = False
        intraday_ok = False

        if "daily" in result:
            daily = result["daily"]
            daily_ok = daily.get("raw_rows", 0) > 0

        if "intraday" in result:
            intraday = result["intraday"]
            intraday_ok = intraday.get("raw_rows", 0) > 0

        if daily_ok or intraday_ok:
            status = "[OK]"
            success_count += 1
        else:
            status = "[FAIL]"

        print(f"{status} {symbol:10} ({yahoo_symbol}): 天级={'OK' if daily_ok else 'FAIL'}, 15分钟={'OK' if intraday_ok else 'FAIL'}")

    print(f"\n成功: {success_count}/{len(symbols)}")

    # 步骤 4: 提示运行 main.py
    print(f"\n{'='*60}")
    print("下一步: 收集情绪数据")
    print(f"{'='*60}")
    print("\n运行以下命令收集情绪数据（24小时）:")
    print("  python main.py --hours 24 --source all")
    print("\n或者指定特定符号:")
    print(f"  python main.py --hours 24 --symbols {' '.join([map_symbol_to_yahoo(s) for s in symbols[:3]])}")

    print(f"\n{'='*60}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[!] 用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
