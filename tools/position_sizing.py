from __future__ import annotations

"""
position_sizing.py - 仓位管理与资金管理

提供三种仓位计算模型:
  ① 固定风险模型  — 每笔交易风险 = 账户权益 × N%，最常用
  ② 凯利公式      — 基于历史胜率和盈亏比优化理论最优仓位
  ③ 波动率调整    — 根据当前 ATR 相对均值动态缩放固定风险仓位

核心思想: 先确定"可以亏多少"，再倒推"能买多少"。
         每笔交易风险 ≤ 账户 1-2%，才能在连续亏损中存活。
"""

import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools.calculate import load_bars, get_recent_24h, format_report


# ==========================================
# 内部工具
# ==========================================

def _get_atr_stats(symbol: str) -> tuple[float, float, float]:
    """
    返回 (current_atr, atr_mean_20, current_price)。
    用于波动率调整仓位的基础数据。
    """
    df = load_bars(symbol)
    if df.empty:
        return 0.0, 0.0, 0.0

    df_24h = get_recent_24h(df)
    if len(df_24h) < 20:
        df_24h = df.tail(96)

    high, low, close = df_24h['high'], df_24h['low'], df_24h['close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(14).mean().dropna()

    if atr_series.empty:
        return 0.0, 0.0, float(close.iloc[-1])

    return float(atr_series.iloc[-1]), float(atr_series.mean()), float(close.iloc[-1])


# ==========================================
# ① 固定风险模型
# ==========================================

def fixed_risk_size(
    account_equity: float,
    entry_price: float,
    stop_loss: float,
    risk_pct: float = 0.01,
) -> dict:
    """
    固定风险模型: 每笔最大亏损 = 账户 × risk_pct

    公式: 数量 = (账户 × 风险%) / |入场价 - 止损价|

    Parameters:
        account_equity: 账户总权益 (如 10000 USDT)
        entry_price:    计划入场价格
        stop_loss:      止损价格
        risk_pct:       单笔风险占比 (默认 0.01 = 1%)

    Returns:
        dict: units, risk_amount, position_value, leverage_needed
    """
    risk_amount = account_equity * risk_pct
    risk_per_unit = abs(entry_price - stop_loss)

    if risk_per_unit < 1e-8:
        return {'error': '入场价与止损价相同，无效参数'}

    units = risk_amount / risk_per_unit
    position_value = units * entry_price
    leverage_needed = position_value / account_equity
    risk_distance_pct = risk_per_unit / entry_price * 100

    return {
        'units': round(units, 6),
        'risk_amount': round(risk_amount, 4),
        'risk_distance_pct': round(risk_distance_pct, 3),
        'position_value': round(position_value, 4),
        'leverage_needed': round(leverage_needed, 3),
        'risk_pct': risk_pct,
    }


# ==========================================
# ② 凯利公式
# ==========================================

def kelly_size(
    account_equity: float,
    win_rate: float,
    avg_rr: float,
    fraction: float = 0.5,
) -> dict:
    """
    凯利公式仓位: f* = W - (1-W)/R

    W = 胜率, R = 盈亏比 (avg_win / avg_loss)

    LLM 指南:
    - 实际使用 半凯利 (fraction=0.5) 避免过度下注
    - Kelly < 0: 期望为负，该策略不值得交易
    - Kelly > 25%: 通常认为过于激进，建议上限 25%

    Parameters:
        account_equity: 账户权益
        win_rate:  历史胜率 (0-1, 如 0.55)
        avg_rr:    历史平均盈亏比 (如 2.0 = 盈利是亏损的2倍)
        fraction:  凯利分数 (默认 0.5 = 半凯利)

    Returns:
        dict: kelly_pct, half_kelly_pct, recommended_equity
    """
    if win_rate <= 0 or win_rate >= 1:
        return {'error': f'胜率 {win_rate} 无效，需在 (0, 1) 范围内'}
    if avg_rr <= 0:
        return {'error': f'盈亏比 {avg_rr} 无效，需大于 0'}

    kelly_raw = win_rate - (1 - win_rate) / avg_rr

    if kelly_raw <= 0:
        return {
            'kelly_pct': round(kelly_raw * 100, 2),
            'note': (f'负凯利 ({kelly_raw*100:.2f}%)，期望收益为负\n'
                     f'  胜率 {win_rate:.0%} + 盈亏比 1:{avg_rr} 不足以产生正期望'),
        }

    recommended_pct = min(kelly_raw * fraction, 0.25)  # 上限 25%
    recommended_equity = account_equity * recommended_pct
    expected_growth = win_rate * np.log(1 + avg_rr * kelly_raw) + \
                      (1 - win_rate) * np.log(1 - kelly_raw)

    return {
        'kelly_pct': round(kelly_raw * 100, 2),
        'half_kelly_pct': round(recommended_pct * 100, 2),
        'recommended_equity': round(recommended_equity, 4),
        'win_rate': win_rate,
        'avg_rr': avg_rr,
        'expected_log_growth': round(expected_growth, 4),
        'capped': recommended_pct < kelly_raw * fraction,  # 是否被25%上限截断
    }


# ==========================================
# ③ 波动率调整仓位
# ==========================================

def volatility_adjusted_size(
    base_units: float,
    current_atr: float,
    avg_atr: float,
    entry_price: float,
    target_atr_pct: float = 0.02,
) -> dict:
    """
    波动率调整: 使每笔交易的"波动暴露"保持恒定。

    逻辑: 当 ATR 高时，价格随机波动更大 → 减仓；
         当 ATR 低时，波动平静 → 可适当加仓。

    公式: adjusted = base × (target_atr_pct / current_atr_pct)
    限制: 调整因子被约束在 [0.3, 2.0] 范围内

    Parameters:
        base_units:      固定风险模型给出的基础仓位
        current_atr:     当前 ATR
        avg_atr:         历史平均 ATR (用于判断相对水平)
        entry_price:     入场价格
        target_atr_pct:  目标波动率占价格的比例 (默认 2%)

    Returns:
        dict: adjusted_units, vol_modifier, vol_ratio, reason
    """
    if avg_atr <= 0 or current_atr <= 0 or entry_price <= 0:
        return {
            'base_units': base_units,
            'adjusted_units': base_units,
            'vol_modifier': 1.0,
            'reason': 'ATR 数据不足，使用原始仓位',
        }

    current_atr_pct = current_atr / entry_price
    vol_modifier = float(np.clip(target_atr_pct / current_atr_pct, 0.3, 2.0))
    vol_ratio = current_atr / avg_atr
    adjusted_units = round(base_units * vol_modifier, 6)

    if vol_ratio > 1.5:
        reason = f'高波动 (ATR {vol_ratio:.2f}x 历史均值) → 减仓至 {vol_modifier:.2f}x'
    elif vol_ratio < 0.7:
        reason = f'低波动 (ATR {vol_ratio:.2f}x 历史均值) → 加仓至 {vol_modifier:.2f}x'
    else:
        reason = f'波动正常 (ATR {vol_ratio:.2f}x 历史均值) → 仓位基本不变 {vol_modifier:.2f}x'

    return {
        'base_units': base_units,
        'adjusted_units': adjusted_units,
        'vol_modifier': round(vol_modifier, 3),
        'vol_ratio': round(vol_ratio, 3),
        'current_atr_pct': round(current_atr_pct * 100, 3),
        'reason': reason,
    }


# ==========================================
# 主函数
# ==========================================

def position_size(
    symbol: str,
    account_equity: float,
    entry_price: float,
    stop_loss: float,
    risk_pct: float = 0.01,
    win_rate: float | None = None,
    avg_rr: float | None = None,
) -> str:
    """
    主函数: 综合输出三种仓位计算方案。

    Parameters:
        symbol:         标的代码 (用于获取 ATR 数据)
        account_equity: 账户权益 (USDT/USD/CNY)
        entry_price:    计划入场价格
        stop_loss:      止损价格
        risk_pct:       单笔风险占比 (默认 0.01 = 1%)
        win_rate:       历史胜率 (可选，填写后输出 Kelly 建议)
        avg_rr:         历史平均盈亏比 (与 win_rate 配合使用)

    Returns:
        str: LLM 可读的仓位管理报告
    """
    current_atr, avg_atr, _ = _get_atr_stats(symbol)

    sections = []
    risk_distance = abs(entry_price - stop_loss)
    risk_distance_pct = risk_distance / entry_price * 100 if entry_price > 0 else 0
    risk_amount = account_equity * risk_pct

    # 基本参数
    sections.append(('交易参数',
                     f'入场: {entry_price}  |  止损: {stop_loss}\n  '
                     f'风险距离: {risk_distance:.6f} ({risk_distance_pct:.3f}%)'))
    sections.append(('账户信息',
                     f'权益: {account_equity:,.2f}  |  '
                     f'单笔风险: {risk_pct*100:.1f}% = {risk_amount:,.4f}'))

    # ── ① 固定风险模型 ───────────────────────────────────
    fr = fixed_risk_size(account_equity, entry_price, stop_loss, risk_pct)
    if 'error' in fr:
        sections.append(('固定风险仓位', f'计算失败: {fr["error"]}'))
    else:
        sections.append(('① 固定风险仓位',
                         f'数量: {fr["units"]}  |  '
                         f'持仓市值: {fr["position_value"]:,.4f}  |  '
                         f'所需杠杆: {fr["leverage_needed"]:.3f}x'))

    # ── ② 波动率调整仓位 ─────────────────────────────────
    if current_atr > 0 and 'error' not in fr:
        va = volatility_adjusted_size(
            fr['units'], current_atr, avg_atr, entry_price, target_atr_pct=0.02
        )
        sections.append(('② 波动率调整仓位',
                         f'调整后数量: {va["adjusted_units"]}  |  '
                         f'修正因子: {va["vol_modifier"]}x\n  '
                         f'当前ATR: {current_atr:.6f} ({va["current_atr_pct"]:.3f}%)  |  '
                         f'{va["reason"]}'))
    elif 'error' not in fr:
        sections.append(('② 波动率调整仓位', '无ATR数据，使用固定风险数量'))

    # ── ③ 凯利公式 (可选) ────────────────────────────────
    if win_rate is not None and avg_rr is not None:
        kelly = kelly_size(account_equity, win_rate, avg_rr)
        if 'error' in kelly:
            sections.append(('③ Kelly仓位', f'计算失败: {kelly["error"]}'))
        elif 'note' in kelly:
            sections.append(('③ Kelly仓位', kelly['note']))
        else:
            cap_note = ' (已截断至25%上限)' if kelly.get('capped') else ''
            sections.append(('③ Kelly仓位',
                             f'Kelly%: {kelly["kelly_pct"]:.2f}%  |  '
                             f'半Kelly(推荐): {kelly["half_kelly_pct"]:.2f}%{cap_note} = {kelly["recommended_equity"]:,.4f}\n  '
                             f'期望对数增长: {kelly["expected_log_growth"]:.4f}/笔  |  '
                             f'胜率: {win_rate:.0%}  盈亏比: 1:{avg_rr}'))
    else:
        sections.append(('③ Kelly仓位', '未提供 win_rate / avg_rr，跳过 (建议回测后填入)'))

    # ── 风险提示 ─────────────────────────────────────────
    warnings = []
    if 'error' not in fr:
        if fr['leverage_needed'] > 5:
            warnings.append(f'⚠ 杠杆 {fr["leverage_needed"]:.1f}x 过高，建议降低 risk_pct 或扩大止损')
        elif fr['leverage_needed'] > 3:
            warnings.append(f'⚠ 杠杆 {fr["leverage_needed"]:.1f}x 偏高，注意资金管理')
    if risk_distance_pct < 0.3:
        warnings.append('⚠ 止损距离 <0.3%，极易被随机噪音触发，建议扩大止损或不入场')
    elif risk_distance_pct < 0.8:
        warnings.append(f'⚠ 止损距离仅 {risk_distance_pct:.2f}%，偏小，易被洗盘')
    if risk_distance_pct > 8:
        warnings.append(f'⚠ 止损距离 {risk_distance_pct:.2f}% 过大，单笔风险过重')
    if risk_pct > 0.02:
        warnings.append(f'⚠ 单笔风险 {risk_pct*100:.1f}% > 2%，激进设置，连续亏损时资金损耗快')

    if warnings:
        sections.append(('风险提示', '\n  '.join(warnings)))

    return format_report(f"{symbol} 仓位管理", sections)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Position Sizing - 仓位管理")
    parser.add_argument("symbol",   help="标的代码 (如 AAPL, BTC)")
    parser.add_argument("account",  type=float, help="账户权益")
    parser.add_argument("entry",    type=float, help="入场价格")
    parser.add_argument("stop",     type=float, help="止损价格")
    parser.add_argument("--risk",   type=float, default=0.01, help="单笔风险占比 (默认 0.01=1%%)")
    parser.add_argument("--winrate", type=float, default=None, help="历史胜率 (可选)")
    parser.add_argument("--rr",     type=float, default=None, help="历史平均盈亏比 (可选)")
    args = parser.parse_args()
    print(position_size(args.symbol, args.account, args.entry, args.stop,
                        args.risk, args.winrate, args.rr))
