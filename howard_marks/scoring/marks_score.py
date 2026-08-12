"""Howard Marks (霍华德·马克斯) scoring framework — pure functions.

Three dimensions, 100 points total:
  1. 周期定位 Cycle Positioning     (40 pts)
  2. 逆向强度 Contrarian Strength   (35 pts)
  3. 风险溢价 Risk Premium          (25 pts)

All functions are PURE: no IO, no global state, no CLI, no logger.
Only QUANTIFIABLE dimensions are coded.  "第二层思维" and qualitative
judgment stay in framework.md documentation only.

Reference: 霍华德·马克斯《周期》《投资最重要的事》
"""

from __future__ import annotations

from typing import Any, Optional


# ══════════════════════════════════════════════════════════════════════════
# Dimension 1: Cycle Positioning (40 pts)
# ══════════════════════════════════════════════════════════════════════════

def _score_cycle_positioning(
    pe_percentile_5y: Optional[float] = None,
    sector_momentum_30d: Optional[float] = None,
    vix: Optional[float] = None,
    credit_spread: Optional[float] = None,
    fed_rate_direction: str = "neutral",
    degrade_to_neutral: bool = False,
) -> tuple[int, str, str]:
    """Score the Cycle Positioning dimension.

    Uses four indicators to build an automatic cycle thermometer:
      1. PE 5-year percentile (valuation cycle)
      2. Sector 30-day momentum (sentiment cycle)
      3. VIX level (fear/greed cycle)
      4. Credit spread (credit cycle)

    High score = late cycle / distress (good entry point for contrarian).
    Low score = early/peak cycle (overheated — wait or reduce).

    Returns:
        (score 0-40, cycle_label, detail)
    """
    if degrade_to_neutral:
        return 20, "周期位置不明", "数据不可用，使用中性分"

    score = 20  # base (mid-cycle)
    signals: list[str] = []
    signal_count = 0

    # 1. PE percentile: high = expensive/optimistic, low = cheap/pessimistic
    if pe_percentile_5y is not None:
        signal_count += 1
        if pe_percentile_5y > 80:
            score -= 8
            signals.append(f"PE在{pe_percentile_5y:.0f}%分位—估值偏高，周期顶部特征")
        elif pe_percentile_5y > 60:
            score -= 3
            signals.append(f"PE在{pe_percentile_5y:.0f}%分位—估值中高")
        elif pe_percentile_5y < 20:
            score += 8
            signals.append(f"PE在{pe_percentile_5y:.0f}%分位—估值低位，周期底部特征")
        elif pe_percentile_5y < 40:
            score += 4
            signals.append(f"PE在{pe_percentile_5y:.0f}%分位—估值偏低")

    # 2. Sector momentum: strong upward = late cycle, declining = opportunity
    if sector_momentum_30d is not None:
        signal_count += 1
        if sector_momentum_30d > 15:
            score -= 7
            signals.append(f"板块30日动量+{sector_momentum_30d:.1f}%—过热，避免追高")
        elif sector_momentum_30d > 8:
            score -= 3
            signals.append(f"板块30日动量+{sector_momentum_30d:.1f}%—偏强")
        elif sector_momentum_30d < -10:
            score += 7
            signals.append(f"板块30日动量{sector_momentum_30d:.1f}%—超跌，逆向机会")
        elif sector_momentum_30d < -5:
            score += 3
            signals.append(f"板块30日动量{sector_momentum_30d:.1f}%—偏弱，值得关注")

    # 3. VIX: high = fear (buy), low = complacency (sell)
    if vix is not None:
        signal_count += 1
        if vix > 30:
            score += 8
            signals.append(f"VIX={vix:.0f}—恐慌区间，逆向买入机会")
        elif vix > 25:
            score += 5
            signals.append(f"VIX={vix:.0f}—偏高，市场担忧")
        elif vix > 20:
            score += 2
            signals.append(f"VIX={vix:.0f}—正常偏高")
        elif vix < 12:
            score -= 6
            signals.append(f"VIX={vix:.0f}—极度安逸，注意风险")
        elif vix < 15:
            score -= 3
            signals.append(f"VIX={vix:.0f}—偏低，市场自满")

    # 4. Credit spread (HY OAS vs Treasury)
    if credit_spread is not None:
        signal_count += 1
        if credit_spread > 6.0:
            score += 6
            signals.append(f"信用利差{credit_spread:.1f}%—信用紧缩，逆向机会")
        elif credit_spread > 4.0:
            score += 3
            signals.append(f"信用利差{credit_spread:.1f}%—偏宽")
        elif credit_spread < 1.5:
            score -= 4
            signals.append(f"信用利差{credit_spread:.1f}%—极度宽松，风险定价不足")

    # 5. Fed rate direction
    if fed_rate_direction == "cutting":
        score += 2
        signals.append("降息周期—利好风险资产")
    elif fed_rate_direction == "hiking":
        score -= 3
        signals.append("加息周期—压制估值")
    signal_count += 1

    # Cycle label
    clamped = max(0, min(40, score))
    if clamped >= 28:
        cycle_label = "周期底部区域 — 适合逐步建仓"
    elif clamped >= 20:
        cycle_label = "周期中段 — 选择性参与"
    elif clamped >= 12:
        cycle_label = "周期偏高 — 谨慎，控制仓位"
    else:
        cycle_label = "周期顶部区域 — 建议等待或减仓"

    detail = "；".join(signals) if signals else f"基于{signal_count}个指标综合判断"
    return clamped, cycle_label, detail


# ══════════════════════════════════════════════════════════════════════════
# Dimension 2: Contrarian Strength (35 pts)
# ══════════════════════════════════════════════════════════════════════════

def _score_contrarian_strength(
    sector_etf_flow_30d: Optional[float] = None,
    short_pct_float: Optional[float] = None,
    analyst_consensus: str = "hold",
    price_vs_200ma_pct: Optional[float] = None,
    insider_trend: str = "neutral",
    degrade_to_neutral: bool = False,
) -> tuple[int, str]:
    """Score the Contrarian Strength dimension.

    Measures how much the market is leaning one way — and whether
    the contrarian position is justified.

    High score = strong contrarian setup (everyone hates it, but
    fundamentals may not justify the pessimism).

    Returns:
        (score 0-35, detail)
    """
    if degrade_to_neutral:
        return 18, "数据不可用，使用中性分"

    score = 15  # base
    signals: list[str] = []

    # 1. ETF flow: outflow = contrarian opportunity (if fundamentals OK)
    if sector_etf_flow_30d is not None:
        if sector_etf_flow_30d < -500:  # $500M+ outflow
            score += 10
            signals.append(f"板块ETF 30日净流出${abs(sector_etf_flow_30d):.0f}M—极度悲观，逆向信号强")
        elif sector_etf_flow_30d < -100:
            score += 5
            signals.append(f"板块ETF 30日净流出${abs(sector_etf_flow_30d):.0f}M—资金撤离")
        elif sector_etf_flow_30d > 500:
            score -= 5
            signals.append(f"板块ETF 30日净流入${sector_etf_flow_30d:.0f}M—资金拥挤")
        elif sector_etf_flow_30d > 200:
            score -= 2
            signals.append("板块ETF资金温和流入—非逆向环境")

    # 2. Short interest: high = crowded negativity (could reverse violently)
    if short_pct_float is not None:
        pct = short_pct_float * 100 if short_pct_float < 1 else short_pct_float
        if pct > 15:
            score += 8
            signals.append(f"空头占比{pct:.1f}%—极端看空，轧空潜力")
        elif pct > 8:
            score += 4
            signals.append(f"空头占比{pct:.1f}%—偏空")
        elif pct < 2:
            score -= 3
            signals.append(f"空头占比{pct:.1f}%—无人看空，可能过度乐观")

    # 3. Analyst consensus
    if analyst_consensus == "strong_sell":
        score += 6
        signals.append("分析师一致看空—极度逆向")
    elif analyst_consensus == "sell":
        score += 3
        signals.append("分析师偏向看空")
    elif analyst_consensus == "strong_buy":
        score -= 4
        signals.append("分析师一致看多—缺乏逆向价值")
    elif analyst_consensus == "buy":
        score -= 2
        signals.append("分析师偏向看多")

    # 4. Price vs 200-day MA — technical contrarian
    if price_vs_200ma_pct is not None:
        if price_vs_200ma_pct < -20:
            score += 7
            signals.append(f"价格低于200日均线{abs(price_vs_200ma_pct):.0f}%—深度超跌")
        elif price_vs_200ma_pct < -10:
            score += 3
            signals.append(f"价格低于200日均线{abs(price_vs_200ma_pct):.0f}%")
        elif price_vs_200ma_pct > 20:
            score -= 4
            signals.append(f"价格高于200日均线{price_vs_200ma_pct:.0f}%—过度延伸")

    # 5. Insider trading trend
    if insider_trend == "buying":
        score += 5
        signals.append("内部人士净买入—最强逆向确认")
    elif insider_trend == "selling":
        score -= 3
        signals.append("内部人士净卖出—谨慎")

    detail = "；".join(signals) if signals else "无显著逆向信号"
    return max(0, min(35, score)), detail


# ══════════════════════════════════════════════════════════════════════════
# Dimension 3: Risk Premium (25 pts)
# ══════════════════════════════════════════════════════════════════════════

def _score_risk_premium(
    equity_risk_premium: Optional[float] = None,
    earnings_yield: Optional[float] = None,
    ten_year_yield: Optional[float] = None,
    credit_spread: Optional[float] = None,
    shiller_pe_percentile: Optional[float] = None,
    degrade_to_neutral: bool = False,
) -> tuple[int, str]:
    """Score the Risk Premium dimension.

    Compares equity returns against risk-free alternatives to determine
    if stocks are adequately compensating for risk.

    High score = high risk premium (stocks cheap vs bonds).
    Low score = low/no risk premium (bonds more attractive).

    Returns:
        (score 0-25, detail)
    """
    if degrade_to_neutral:
        return 13, "数据不可用，使用中性分"

    score = 10  # base
    signals: list[str] = []

    # 1. Equity Risk Premium (ERP = earnings yield - 10Y Treasury)
    if equity_risk_premium is not None:
        if equity_risk_premium > 0.05:
            score += 8
            signals.append(f"ERP={equity_risk_premium:.1%}—股票极具吸引力")
        elif equity_risk_premium > 0.03:
            score += 5
            signals.append(f"ERP={equity_risk_premium:.1%}—股票有吸引力")
        elif equity_risk_premium > 0.01:
            score += 2
            signals.append(f"ERP={equity_risk_premium:.1%}—股票略微优于债券")
        elif equity_risk_premium < 0:
            score -= 6
            signals.append(f"ERP={equity_risk_premium:.1%}—债券优于股票！")
        elif equity_risk_premium < 0.01:
            score -= 2
            signals.append(f"ERP={equity_risk_premium:.1%}—风险溢价不足")

    # 2. Earnings yield (absolute)
    if earnings_yield is not None:
        if earnings_yield > 0.08:
            score += 5
            signals.append(f"盈利收益率{earnings_yield:.1%}—高回报")
        elif earnings_yield > 0.05:
            score += 3
            signals.append(f"盈利收益率{earnings_yield:.1%}—合理")
        elif earnings_yield < 0.02:
            score -= 3
            signals.append(f"盈利收益率{earnings_yield:.1%}—极低")

    # 3. Credit spread (risk appetite barometer)
    if credit_spread is not None:
        if credit_spread > 5.0:
            score += 3
            signals.append("信用利差宽—风险被定价，逆向机会")
        elif credit_spread < 1.5:
            score -= 3
            signals.append("信用利差窄—风险定价可能不足")

    # 4. Shiller CAPE percentile
    if shiller_pe_percentile is not None:
        if shiller_pe_percentile > 90:
            score -= 5
            signals.append(f"CAPE在{shiller_pe_percentile:.0f}%分位—历史极度高估")
        elif shiller_pe_percentile > 75:
            score -= 2
            signals.append(f"CAPE在{shiller_pe_percentile:.0f}%分位—偏高")
        elif shiller_pe_percentile < 25:
            score += 4
            signals.append(f"CAPE在{shiller_pe_percentile:.0f}%分位—历史低估区间")

    # 5. 10Y as opportunity cost
    if ten_year_yield is not None:
        if ten_year_yield > 0.06:
            score -= 2
            signals.append(f"10Y={ten_year_yield:.1%}—无风险利率高，股票吸引力下降")

    detail = "；".join(signals) if signals else "无足够数据判断风险溢价"
    return max(0, min(25, score)), detail


# ══════════════════════════════════════════════════════════════════════════
# Main scoring function
# ══════════════════════════════════════════════════════════════════════════

def score_marks(
    symbol: str,
    *,
    fundamentals: Optional[dict[str, Any]] = None,
    # Cycle Positioning
    pe_percentile_5y: Optional[float] = None,
    sector_momentum_30d: Optional[float] = None,
    vix: Optional[float] = None,
    credit_spread: Optional[float] = None,
    fed_rate_direction: str = "neutral",
    # Contrarian Strength
    sector_etf_flow_30d: Optional[float] = None,
    short_pct_float: Optional[float] = None,
    analyst_consensus: str = "hold",
    price_vs_200ma_pct: Optional[float] = None,
    insider_trend: str = "neutral",
    # Risk Premium
    equity_risk_premium: Optional[float] = None,
    earnings_yield: Optional[float] = None,
    ten_year_yield: Optional[float] = None,
    shiller_pe_percentile: Optional[float] = None,
    # Degradation
    degrade_to_neutral: bool = False,
) -> dict[str, Any]:
    """Score market conditions through Howard Marks' three-dimension framework.

    Dimensions (total 100 pts):
      1. 周期定位 Cycle Positioning     (40)
      2. 逆向强度 Contrarian Strength   (35)
      3. 风险溢价 Risk Premium          (25)

    Note: Howard Marks' framework is primarily about market timing and
    risk posture, not individual stock selection.  This scoring tells
    you "is NOW a good time to buy risk assets?" rather than "is THIS
    stock a good buy?"

    All data must be passed in explicitly.  This function is pure.

    Args:
        symbol: Ticker symbol (for output identification)
        fundamentals: Optional pre-fetched fundamentals dict.  Keys used:
            pe_percentile_5y, short_pct_float, earnings_yield
        degrade_to_neutral: All dimensions return neutral on data outage

    Returns:
        {
            symbol, framework: "marks", total (0-100), max_score: 100,
            passed: bool (total >= 50), verdict, cycle_label,
            dimensions: {label: {score, max, detail}, ...},
            generated_at: ISO timestamp,
            degraded: bool,
        }
    """
    fund = fundamentals or {}

    # Merge fundamentals into explicit params
    pe_percentile_5y = pe_percentile_5y if pe_percentile_5y is not None else fund.get("pe_percentile_5y")
    short_pct_float = short_pct_float if short_pct_float is not None else fund.get("short_pct_float")
    earnings_yield = earnings_yield if earnings_yield is not None else fund.get("earnings_yield")
    credit_spread = credit_spread if credit_spread is not None else fund.get("credit_spread")

    # ── Score each dimension ──
    dim1, cycle_label, d1_detail = _score_cycle_positioning(
        pe_percentile_5y, sector_momentum_30d, vix, credit_spread,
        fed_rate_direction, degrade_to_neutral)
    dim2, d2_detail = _score_contrarian_strength(
        sector_etf_flow_30d, short_pct_float, analyst_consensus,
        price_vs_200ma_pct, insider_trend, degrade_to_neutral)
    dim3, d3_detail = _score_risk_premium(
        equity_risk_premium, earnings_yield, ten_year_yield,
        credit_spread, shiller_pe_percentile, degrade_to_neutral)

    total = dim1 + dim2 + dim3
    degraded = degrade_to_neutral

    # ── Verdict ──
    PASS_THRESHOLD = 50
    if total >= 70:
        verdict = "极度悲观时的买入良机 — 大举建仓"
    elif total >= PASS_THRESHOLD:
        verdict = "逆向条件具备 — 可逐步建仓"
    elif total >= 30:
        verdict = "周期中性 — 控制节奏，选择性参与"
    else:
        verdict = "周期过热/风险溢价不足 — 暂缓买入，等待回调"

    from datetime import datetime, timezone, timedelta
    return {
        "symbol": symbol,
        "framework": "marks",
        "total": total,
        "max_score": 100,
        "pass_threshold": PASS_THRESHOLD,
        "passed": total >= PASS_THRESHOLD,
        "verdict": verdict,
        "cycle_label": cycle_label,
        "dimensions": {
            "周期定位":   {"score": dim1, "max": 40, "detail": d1_detail},
            "逆向强度":   {"score": dim2, "max": 35, "detail": d2_detail},
            "风险溢价":   {"score": dim3, "max": 25, "detail": d3_detail},
        },
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "degraded": degraded,
    }
