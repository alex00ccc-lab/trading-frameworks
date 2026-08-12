"""Duan Yongping (段永平) scoring framework — pure functions.

Four dimensions, 100 points total:
  1. 能力圈 Circle of Competence (25 pts)
  2. 安全边际 Margin of Safety    (30 pts)
  3. 护城河 Moat                   (25 pts)
  4. 好生意 Good Business          (20 pts)

All functions are PURE: no IO, no global state, no CLI, no logger.
Only QUANTIFIABLE dimensions are coded.  Non-quantifiable dimensions
("企业文化", "管理层诚信") stay in framework.md documentation only.

Reference: 段永平投资方法论
"""

from __future__ import annotations

from typing import Any, Optional


# ══════════════════════════════════════════════════════════════════════════
# Dimension 1: Circle of Competence (25 pts)
# ══════════════════════════════════════════════════════════════════════════

def _score_circle_of_competence(
    competence_level: str = "YELLOW",
    obsidian_note_words: int = 0,
    trade_count: int = 0,
    sector_familiarity: float = 0.5,
) -> tuple[int, str]:
    """Score the Circle of Competence dimension.

    Auto-determined from:
      - Obsidian note word count (depth of research)
      - Historical trade count (familiarity through experience)
      - Sector familiarity score (0-1 from known sectors)

    Args:
        competence_level: "GREEN" | "YELLOW" | "RED" (pre-computed)
        obsidian_note_words: Word count of related Obsidian notes
        trade_count: Number of historical trades in this sector/symbol
        sector_familiarity: 0.0-1.0 score based on known sectors

    Returns:
        (score 0-25, detail string)
    """
    # Explicit level takes precedence
    if competence_level == "GREEN":
        return 25, "能力圈内 — 深度研究 + 多笔交易经验"
    if competence_level == "RED":
        return 0, "能力圈外 — 无研究笔记，无交易经验，不建议参与"

    # YELLOW: compute sub-score from available signals
    score = 10  # base YELLOW

    if obsidian_note_words >= 2000:
        score += 8
        detail = "研究充分(≥2000字笔记)"
    elif obsidian_note_words >= 500:
        score += 5
        detail = "有一定研究(500-2000字笔记)"
    else:
        score += 2
        detail = "研究不足(<500字笔记)"

    if trade_count >= 5:
        score += 7
        detail += " + 多次交易经验"
    elif trade_count >= 2:
        score += 4
        detail += " + 少量交易经验"
    else:
        score += 0
        detail += "，无交易经验"

    if sector_familiarity >= 0.8:
        score += 2  # bonus but capped
        detail += "，行业熟悉度高"

    return min(score, 25), detail


# ══════════════════════════════════════════════════════════════════════════
# Dimension 2: Margin of Safety (30 pts)
# ══════════════════════════════════════════════════════════════════════════

def _score_margin_of_safety(
    pe: Optional[float] = None,
    pe_percentile_5y: Optional[float] = None,
    price_to_book: Optional[float] = None,
    fcf_yield: Optional[float] = None,
    discount_to_intrinsic_pct: Optional[float] = None,
    degrade_to_neutral: bool = False,
) -> tuple[int, str]:
    """Score the Margin of Safety dimension.

    Higher score = deeper discount to intrinsic value.

    Args:
        pe: Current P/E ratio
        pe_percentile_5y: PE as percentile of 5-year range (0-100)
        price_to_book: P/B ratio
        fcf_yield: Free cash flow yield
        discount_to_intrinsic_pct: Explicit discount estimate (e.g. 20 = 20% below IV)
        degrade_to_neutral: Return neutral score during data outages

    Returns:
        (score 0-30, detail string)
    """
    if degrade_to_neutral:
        return 15, "数据不可用，使用中性分"

    score = 10  # base
    signals: list[str] = []

    # PE percentile (most important for safety)
    if pe_percentile_5y is not None:
        if pe_percentile_5y < 20:
            score += 10
            signals.append(f"PE位于5年{pe_percentile_5y:.0f}%低位")
        elif pe_percentile_5y < 40:
            score += 6
            signals.append(f"PE位于5年{pe_percentile_5y:.0f}%偏低")
        elif pe_percentile_5y < 60:
            score += 2
            signals.append(f"PE位于5年{pe_percentile_5y:.0f}%中位")
        elif pe_percentile_5y > 80:
            score -= 5
            signals.append(f"PE位于5年{pe_percentile_5y:.0f}%高位—安全边际不足")

    # Absolute PE
    if pe is not None:
        if pe < 0:
            score -= 8
            signals.append("PE为负—无法判断安全边际")
        elif pe < 12:
            score += 5
            signals.append(f"PE={pe:.1f}—绝对估值偏低")
        elif pe < 18:
            score += 2
            signals.append(f"PE={pe:.1f}—估值合理")
        elif pe > 35:
            score -= 5
            signals.append(f"PE={pe:.1f}—估值偏高")

    # FCF yield (cash return on investment)
    if fcf_yield is not None:
        if fcf_yield > 0.05:
            score += 8
            signals.append(f"FCF收益率{fcf_yield:.1%}—现金流充沛")
        elif fcf_yield > 0.03:
            score += 4
            signals.append(f"FCF收益率{fcf_yield:.1%}—现金流良好")
        elif fcf_yield < 0:
            score -= 5
            signals.append("FCF为负—现金流风险")

    # Explicit discount to intrinsic value
    if discount_to_intrinsic_pct is not None:
        if discount_to_intrinsic_pct > 30:
            score += 7
            signals.append(f"折价{discount_to_intrinsic_pct:.0f}%—深度价值")
        elif discount_to_intrinsic_pct > 15:
            score += 4
            signals.append(f"折价{discount_to_intrinsic_pct:.0f}%—有安全边际")
        elif discount_to_intrinsic_pct > 0:
            score += 2
        else:
            score -= 3
            signals.append("高于内在价值—无安全边际")

    # P/B sanity
    if price_to_book is not None and price_to_book > 10:
        score -= 3
        signals.append(f"P/B={price_to_book:.1f}—资产溢价过高")

    detail = "；".join(signals) if signals else "无足够数据判断安全边际"
    return max(0, min(30, score)), detail


# ══════════════════════════════════════════════════════════════════════════
# Dimension 3: Moat (25 pts)
# ══════════════════════════════════════════════════════════════════════════

def _score_moat(
    roic: Optional[float] = None,
    gross_margin: Optional[float] = None,
    operating_margin: Optional[float] = None,
    market_share_rank: Optional[int] = None,
    sector_cr3_pct: Optional[float] = None,
    degrade_to_neutral: bool = False,
) -> tuple[int, str]:
    """Score the Moat dimension.

    Measures the durability and width of competitive advantage.

    Args:
        roic: Return on Invested Capital
        gross_margin: Gross margin
        operating_margin: Operating margin
        market_share_rank: Rank in market (1 = leader)
        sector_cr3_pct: CR3 concentration ratio of sector
        degrade_to_neutral: Return neutral score during data outages

    Returns:
        (score 0-25, detail string)
    """
    if degrade_to_neutral:
        return 13, "数据不可用，使用中性分"

    score = 8  # base
    signals: list[str] = []

    # ROIC — the single best moat indicator
    if roic is not None:
        if roic > 0.20:
            score += 10
            signals.append(f"ROIC={roic:.1%}—极强资本回报(>20%)")
        elif roic > 0.12:
            score += 7
            signals.append(f"ROIC={roic:.1%}—优秀资本回报(>12%)")
        elif roic > 0.08:
            score += 4
            signals.append(f"ROIC={roic:.1%}—合格资本回报(>8%)")
        elif roic > 0:
            score += 1
            signals.append(f"ROIC={roic:.1%}—资本回报偏低")
        else:
            score -= 5
            signals.append("ROIC为负—资本毁灭")

    # Gross margin — pricing power proxy
    if gross_margin is not None:
        gm_pct = gross_margin * 100 if gross_margin < 1 else gross_margin
        if gm_pct > 60:
            score += 7
            signals.append(f"毛利率{gm_pct:.0f}%—强定价权")
        elif gm_pct > 40:
            score += 4
            signals.append(f"毛利率{gm_pct:.0f}%—有一定定价权")
        elif gm_pct > 20:
            score += 1
            signals.append(f"毛利率{gm_pct:.0f}%—定价权弱")
        else:
            score -= 3
            signals.append(f"毛利率{gm_pct:.0f}%—几乎无定价权")

    # Operating margin — efficiency
    if operating_margin is not None:
        op_pct = operating_margin * 100 if operating_margin < 1 else operating_margin
        if op_pct > 25:
            score += 4
        elif op_pct < 5:
            score -= 2

    # Market position
    if market_share_rank is not None:
        if market_share_rank == 1:
            score += 4
            signals.append("行业龙头")
        elif market_share_rank <= 3:
            score += 2
            signals.append(f"行业第{market_share_rank}名")
        else:
            score += 0

    # Industry structure (concentrated = better moats)
    if sector_cr3_pct is not None:
        if sector_cr3_pct > 60:
            score += 2
            signals.append(f"行业CR3={sector_cr3_pct:.0f}%—集中度高")

    detail = "；".join(signals) if signals else "无足够数据判断护城河"
    return max(0, min(25, score)), detail


# ══════════════════════════════════════════════════════════════════════════
# Dimension 4: Good Business (20 pts)
# ══════════════════════════════════════════════════════════════════════════

def _score_good_business(
    roe: Optional[float] = None,
    fcf_yield: Optional[float] = None,
    revenue_growth_3y_avg: Optional[float] = None,
    earnings_growth_3y_avg: Optional[float] = None,
    dividend_yield: Optional[float] = None,
    debt_equity: Optional[float] = None,
    degrade_to_neutral: bool = False,
) -> tuple[int, str]:
    """Score the Good Business dimension.

    A good business generates consistent, growing free cash flow with
    high returns on equity and manageable leverage.

    Args:
        roe: Return on Equity
        fcf_yield: Free Cash Flow yield
        revenue_growth_3y_avg: Average annual revenue growth over 3 years
        earnings_growth_3y_avg: Average annual earnings growth over 3 years
        dividend_yield: Dividend yield
        debt_equity: Debt-to-equity ratio
        degrade_to_neutral: Return neutral score during data outages

    Returns:
        (score 0-20, detail string)
    """
    if degrade_to_neutral:
        return 10, "数据不可用，使用中性分"

    score = 8  # base
    signals: list[str] = []

    # ROE (DuPont root)
    if roe is not None:
        if roe > 0.25:
            score += 5
            signals.append(f"ROE={roe:.1%}—优秀(>25%)")
        elif roe > 0.15:
            score += 3
            signals.append(f"ROE={roe:.1%}—良好(>15%)")
        elif roe > 0.08:
            score += 1
            signals.append(f"ROE={roe:.1%}—一般(>8%)")
        elif roe < 0:
            score -= 5
            signals.append("ROE为负—亏损企业")

    # Consistent growth
    if revenue_growth_3y_avg is not None:
        if revenue_growth_3y_avg > 15:
            score += 4
            signals.append(f"3年营收CAGR={revenue_growth_3y_avg:.1f}%—高增长")
        elif revenue_growth_3y_avg > 5:
            score += 3
            signals.append(f"3年营收CAGR={revenue_growth_3y_avg:.1f}%—稳定增长")
        elif revenue_growth_3y_avg >= 0:
            score += 1
            signals.append("营收低速增长")
        else:
            score -= 3
            signals.append(f"3年营收负增长({revenue_growth_3y_avg:.1f}%)")

    if earnings_growth_3y_avg is not None:
        if earnings_growth_3y_avg < -10:
            score -= 3
            signals.append("盈利持续下滑")

    # FCF generation
    if fcf_yield is not None:
        if fcf_yield >= 0.05:
            score += 3
        elif fcf_yield < 0:
            score -= 2
            signals.append("自由现金流为负")

    # Leverage check
    if debt_equity is not None:
        if debt_equity > 2.0:
            score -= 4
            signals.append(f"D/E={debt_equity:.1f}—高杠杆")
        elif debt_equity > 1.0:
            score -= 1
            signals.append(f"D/E={debt_equity:.1f}—中等杠杆")
        else:
            score += 1
            # low leverage is good but don't over-reward it

    # Dividend as quality signal
    if dividend_yield is not None and dividend_yield > 0:
        if 0.02 <= dividend_yield <= 0.06:
            score += 1
            # sustainable dividend = sign of quality

    detail = "；".join(signals) if signals else "无足够数据判断生意质量"
    return max(0, min(20, score)), detail


# ══════════════════════════════════════════════════════════════════════════
# Main scoring function
# ══════════════════════════════════════════════════════════════════════════

def score_duan(
    symbol: str,
    *,
    fundamentals: Optional[dict[str, Any]] = None,
    # Circle of Competence
    competence_level: str = "YELLOW",
    obsidian_note_words: int = 0,
    trade_count: int = 0,
    sector_familiarity: float = 0.5,
    # Margin of Safety (from fundamentals or explicit)
    pe: Optional[float] = None,
    pe_percentile_5y: Optional[float] = None,
    price_to_book: Optional[float] = None,
    fcf_yield: Optional[float] = None,
    discount_to_intrinsic_pct: Optional[float] = None,
    # Moat
    roic: Optional[float] = None,
    gross_margin: Optional[float] = None,
    operating_margin: Optional[float] = None,
    market_share_rank: Optional[int] = None,
    sector_cr3_pct: Optional[float] = None,
    # Good Business
    roe: Optional[float] = None,
    revenue_growth_3y_avg: Optional[float] = None,
    earnings_growth_3y_avg: Optional[float] = None,
    dividend_yield: Optional[float] = None,
    debt_equity: Optional[float] = None,
    # Degradation
    degrade_to_neutral: bool = False,
) -> dict[str, Any]:
    """Score a stock against Duan Yongping's four-dimension framework.

    Dimensions (total 100 pts):
      1. 能力圈 Circle of Competence (25)
      2. 安全边际 Margin of Safety    (30)
      3. 护城河 Moat                   (25)
      4. 好生意 Good Business          (20)

    All data must be passed in explicitly.  This function does NOT fetch
    any data itself — it is a pure computation.

    Args:
        symbol: Ticker symbol
        fundamentals: Optional pre-fetched fundamentals dict.  Keys used:
            pe, pe_percentile_5y, price_to_book, fcf_yield, roic,
            gross_margin, operating_margin, roe, revenue_growth_3y_avg,
            earnings_growth_3y_avg, dividend_yield, debt_equity
        degrade_to_neutral: All dimensions return neutral on data outage

    Returns:
        {
            symbol, framework: "duan", total (0-100), max_score: 100,
            passed: bool (total >= 60), verdict,
            dimensions: {label: {score, max, detail}, ...},
            generated_at: ISO timestamp,
            degraded: bool,
        }
    """
    # Merge fundamentals into explicit params (explicit params win)
    fund = fundamentals or {}
    pe = pe if pe is not None else fund.get("pe")
    pe_percentile_5y = pe_percentile_5y if pe_percentile_5y is not None else fund.get("pe_percentile_5y")
    price_to_book = price_to_book if price_to_book is not None else fund.get("price_to_book")
    fcf_yield = fcf_yield if fcf_yield is not None else fund.get("fcf_yield")
    discount_to_intrinsic_pct = discount_to_intrinsic_pct if discount_to_intrinsic_pct is not None else fund.get("discount_to_intrinsic_pct")
    roic = roic if roic is not None else fund.get("roic")
    gross_margin = gross_margin if gross_margin is not None else fund.get("gross_margin")
    operating_margin = operating_margin if operating_margin is not None else fund.get("operating_margin")
    market_share_rank = market_share_rank if market_share_rank is not None else fund.get("market_share_rank")
    sector_cr3_pct = sector_cr3_pct if sector_cr3_pct is not None else fund.get("sector_cr3_pct")
    roe = roe if roe is not None else fund.get("roe")
    revenue_growth_3y_avg = revenue_growth_3y_avg if revenue_growth_3y_avg is not None else fund.get("revenue_growth_3y_avg")
    earnings_growth_3y_avg = earnings_growth_3y_avg if earnings_growth_3y_avg is not None else fund.get("earnings_growth_3y_avg")
    dividend_yield = dividend_yield if dividend_yield is not None else fund.get("dividend_yield")
    debt_equity = debt_equity if debt_equity is not None else fund.get("debt_equity")

    # ── Score each dimension ──
    dim1, d1_detail = _score_circle_of_competence(
        competence_level, obsidian_note_words, trade_count, sector_familiarity)
    dim2, d2_detail = _score_margin_of_safety(
        pe, pe_percentile_5y, price_to_book, fcf_yield,
        discount_to_intrinsic_pct, degrade_to_neutral)
    dim3, d3_detail = _score_moat(
        roic, gross_margin, operating_margin, market_share_rank,
        sector_cr3_pct, degrade_to_neutral)
    dim4, d4_detail = _score_good_business(
        roe, fcf_yield, revenue_growth_3y_avg, earnings_growth_3y_avg,
        dividend_yield, debt_equity, degrade_to_neutral)

    total = dim1 + dim2 + dim3 + dim4
    degraded = degrade_to_neutral

    # ── Verdict ──
    PASS_THRESHOLD = 60
    if total >= 80:
        verdict = "优秀 — 四个维度都过关，可大胆建仓"
    elif total >= PASS_THRESHOLD:
        verdict = "通过 — 可建仓，关注低分维度改善"
    elif total >= 40:
        verdict = "暂缓 — 多个维度不达标，等待更好的价格或基本面改善"
    else:
        verdict = "否决 — 不在能力圈，或无安全边际，禁止买入"

    from datetime import datetime, timezone, timedelta
    return {
        "symbol": symbol,
        "framework": "duan",
        "total": total,
        "max_score": 100,
        "pass_threshold": PASS_THRESHOLD,
        "passed": total >= PASS_THRESHOLD,
        "verdict": verdict,
        "dimensions": {
            "能力圈":           {"score": dim1, "max": 25, "detail": d1_detail},
            "安全边际":         {"score": dim2, "max": 30, "detail": d2_detail},
            "护城河":           {"score": dim3, "max": 25, "detail": d3_detail},
            "好生意":           {"score": dim4, "max": 20, "detail": d4_detail},
        },
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "degraded": degraded,
    }
