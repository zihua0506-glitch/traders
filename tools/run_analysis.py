"""
run_analysis.py - 端到端分析管道

运行整个"情绪驱动 + 价量验证"的分析流程。
按照 prompt.md 描述的逻辑:
1. 读取情绪数据 → 了解市场看法
2. 获取关键价位 (具体数值)
3. 根据情绪特征动态选择价量工具
4. 输出带确切数值的操作建议

用法:
    python -m trader.tools.run_analysis NVDA
    python -m trader.tools.run_analysis AAPL --hours 48
    python -m trader.tools.run_analysis TSLA --compare SPY
"""

import sys
import os
import argparse

# 将 trader 目录加入 path 以便模块内部 import 正常工作
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from trader.tools.calculate import (
    load_bars, load_sentiment, format_sentiment_report, get_concrete_price
)
from trader.tools.smart_money import smart_money
from trader.tools.trend_structure import trend_structure
from trader.tools.market_psychology import market_psychology
from trader.tools.votality_risk import volatility_risk
from trader.tools.macro_lines import macro_lines
from trader.tools.alpha import alpha_factors


def select_tools(sentiment_data: dict) -> list:
    """
    根据情绪数据动态选择需要调用的价量工具。
    返回: [(工具函数, 工具名称, 调用原因), ...]
    """
    score = sentiment_data.get('weighted_score', 0)
    total = sentiment_data.get('total', 0)

    tools = []

    if total < 5:
        # 数据不足 → 全量调用
        tools = [
            (macro_lines, "宏观均线", "情绪数据不足，全量分析"),
            (trend_structure, "市场结构", "情绪数据不足，全量分析"),
            (smart_money, "机构资金", "情绪数据不足，全量分析"),
            (market_psychology, "市场情绪指标", "情绪数据不足，全量分析"),
            (volatility_risk, "风控波动", "情绪数据不足，全量分析"),
            (alpha_factors, "Alpha因子", "情绪数据不足，全量分析"),
        ]
    elif score > 0.5:
        # 极度看多 → 检查是否过热
        tools = [
            (market_psychology, "市场情绪指标", "极度看多 → 检查超买"),
            (smart_money, "机构资金", "极度看多 → 检查出货信号"),
            (volatility_risk, "风控波动", "极度看多 → 检查波动率过高"),
        ]
    elif score > 0.15:
        # 偏多 → 确认趋势 + 资金支持
        tools = [
            (macro_lines, "宏观均线", "偏多 → 确认大方向"),
            (trend_structure, "市场结构", "偏多 → 确认趋势结构"),
            (smart_money, "机构资金", "偏多 → 确认资金支持"),
        ]
    elif score > -0.15:
        # 中性 → 判断震荡 vs 变盘
        tools = [
            (volatility_risk, "风控波动", "中性 → 检查 CHOP/Squeeze"),
            (alpha_factors, "Alpha因子", "中性 → 检查 Hurst 判断趋势"),
            (macro_lines, "宏观均线", "中性 → 确认宏观位置"),
        ]
    elif score > -0.5:
        # 偏空 → 检查超跌反弹
        tools = [
            (market_psychology, "市场情绪指标", "偏空 → 检查超卖"),
            (trend_structure, "市场结构", "偏空 → 检查支撑位"),
            (smart_money, "机构资金", "偏空 → 检查低位吸筹"),
            (macro_lines, "宏观均线", "偏空 → 检查关键均线"),
        ]
    else:
        # 极度看空 → 恐慌买点?
        tools = [
            (market_psychology, "市场情绪指标", "极度看空 → 检查超卖极端"),
            (smart_money, "机构资金", "极度看空 → 检查 CMF 是否转正"),
            (macro_lines, "宏观均线", "极度看空 → 检查是否跌破 MA200"),
            (alpha_factors, "Alpha因子", "极度看空 → 检查崩盘风险"),
        ]

    return tools


def generate_judgment(sentiment_data: dict, tool_reports: list, price_data: dict) -> str:
    """
    根据情绪 + 价量分析结果，生成综合判断和操作建议。
    """
    lines = []

    # === 综合判断 ===
    lines.append("\n" + "=" * 50)
    lines.append("=== 综合判断 ===")
    lines.append("=" * 50)

    score = sentiment_data.get('weighted_score', 0)
    label = sentiment_data.get('sentiment_label', '无数据')

    # 简化的判断逻辑 (实际应由 LLM 完成更精细的分析)
    if score > 0.15:
        direction = "看多"
    elif score < -0.15:
        direction = "看空"
    else:
        direction = "观望"

    confidence = "中"
    total = sentiment_data.get('total', 0)
    if total >= 20 and abs(score) > 0.3:
        confidence = "中偏高"
    elif total < 5:
        confidence = "低 (情绪数据不足)"

    lines.append(f"方向: {direction}")
    lines.append(f"置信度: {confidence}")
    lines.append(f"情绪驱动: {label} (得分 {score:+.3f})")

    # === 具体操作建议 ===
    if price_data:
        lines.append("")
        lines.append("=" * 50)
        lines.append("=== 具体操作建议 ===")
        lines.append("=" * 50)
        lines.append(f"当前价格: ${price_data['current_price']:.2f}")
        lines.append(f"VWAP: ${price_data['vwap']:.2f} "
                     f"({'价格高于 VWAP' if price_data['current_price'] > price_data['vwap'] else '价格低于 VWAP'} "
                     f"{abs(price_data['current_price'] - price_data['vwap']) / price_data['vwap'] * 100:+.2f}%)")
        lines.append(f"ATR: ${price_data['atr']:.4f}")
        lines.append(f"做多止损: ${price_data['stop_loss_long']:.2f} (= 价格 - 2×ATR)")
        lines.append(f"做空止损: ${price_data['stop_loss_short']:.2f} (= 价格 + 2×ATR)")
        lines.append(f"做多止盈: ${price_data['take_profit_long']:.2f} (= 价格 + 3×ATR)")
        lines.append(f"做空止盈: ${price_data['take_profit_short']:.2f} (= 价格 - 3×ATR)")
        lines.append(f"24h 高点: ${price_data['high_24h']:.2f} / 低点: ${price_data['low_24h']:.2f}")

    lines.append("")
    lines.append("时间框架: 2-4 小时有效 (基于短周期数据)")
    lines.append("注意: 以上为自动化分析结果，完整版应由 LLM 结合上下文进行更精细的推理")

    return "\n".join(lines)


def run_analysis(symbol: str, hours: int = 24, compare: str = None):
    """执行完整分析流程。"""
    print(f"\n{'#' * 60}")
    print(f"# 分析标的: {symbol}")
    print(f"# 情绪窗口: 过去 {hours} 小时")
    if compare:
        print(f"# 对比标的: {compare}")
    print(f"{'#' * 60}")

    # ===== Step 1: 情绪数据 =====
    print("\n" + "=" * 50)
    print("=== Step 1: 读取情绪数据 ===")
    print("=" * 50)

    sentiment_report = format_sentiment_report(symbol, hours)
    sentiment_data = load_sentiment(symbol, hours)
    print(sentiment_report)
    print(f"\n[内部数据] weighted_score={sentiment_data['weighted_score']:+.3f}, "
          f"total={sentiment_data['total']}, label={sentiment_data['sentiment_label']}")

    # ===== Step 2: 关键价位 =====
    print("\n" + "=" * 50)
    print("=== Step 2: 获取关键价位 ===")
    print("=" * 50)

    price_data = get_concrete_price(symbol)
    if price_data:
        print(f"当前价格: ${price_data['current_price']:.2f}")
        print(f"VWAP: ${price_data['vwap']:.2f}")
        print(f"ATR: ${price_data['atr']:.4f}")
        print(f"做多止损: ${price_data['stop_loss_long']:.2f}")
        print(f"做多止盈: ${price_data['take_profit_long']:.2f}")
        print(f"24h 范围: ${price_data['low_24h']:.2f} ~ ${price_data['high_24h']:.2f}")
    else:
        print(f"无法获取 {symbol} 的价格数据")

    # ===== Step 3: 情绪驱动工具选择 =====
    print("\n" + "=" * 50)
    print("=== Step 3: 情绪驱动工具选择 ===")
    print("=" * 50)

    tools = select_tools(sentiment_data)
    print(f"情绪判断: {sentiment_data['sentiment_label']}")
    print(f"选择工具 ({len(tools)} 个):")
    for _, name, reason in tools:
        print(f"  - {name}: {reason}")

    # ===== Step 4: 执行价量分析 =====
    print("\n" + "=" * 50)
    print("=== Step 4: 执行价量分析 ===")
    print("=" * 50)

    tool_reports = []
    for func, name, reason in tools:
        print(f"\n--- {name} ---")
        try:
            if compare:
                result = func(symbol, compare)
            else:
                result = func(symbol)
            print(result)
            tool_reports.append((name, result))
        except Exception as e:
            error_msg = f"[错误] {name}: {e}"
            print(error_msg)
            tool_reports.append((name, error_msg))

    # ===== Step 5: 综合判断 =====
    judgment = generate_judgment(sentiment_data, tool_reports, price_data)
    print(judgment)


def main():
    parser = argparse.ArgumentParser(description="LLM Trader 端到端分析管道")
    parser.add_argument("symbol", help="股票代码 (如 AAPL, NVDA, TSLA)")
    parser.add_argument("--hours", type=int, default=24, help="情绪数据回溯小时数 (默认 24)")
    parser.add_argument("--compare", type=str, default=None, help="对比标的 (如 SPY)")
    args = parser.parse_args()

    run_analysis(args.symbol.upper(), args.hours, args.compare)


if __name__ == "__main__":
    main()
