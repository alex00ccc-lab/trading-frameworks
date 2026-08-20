"""Dong Yiting dual-track scoring framework — pure functions.

Three tracks:
  - Defensive (防御股): 5 dimensions, 100 pts total
  - Cyclical  (周期股): 5 dimensions, 100 pts total
  - Growth    (成长股): 5 dimensions, 100 pts total

All functions are PURE: no IO, no global state, no CLI, no logger.
All external data (fundamentals, market data) must be passed in explicitly.

Reference: 董艺婷资产配置框架 §3.1-3.3
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


_FRAME_CONST_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "frame_const.yaml"


def _load_frame_const() -> dict[str, Any]:
    """模块级一次性加载 frame_const.yaml(同子模块内);失败回退 {}。

    本模块为纯函数模块(无 per-call IO),此处仅在 import 时读一次配置作为模块常量;
    yaml 缺失/损坏时由下方 _FALLBACK 常量保证原行为不变(零行为变化)。
    """
    try:
        with open(_FRAME_CONST_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_FRAME_CONST = _load_frame_const()
_SECTORS_CFG = _FRAME_CONST.get("sectors", {})


# ══════════════════════════════════════════════════════════════════════════
# Sector classification
# ══════════════════════════════════════════════════════════════════════════

_DEFENSIVE_SECTORS_FALLBACK = {
    "Consumer Staples", "Healthcare", "Utilities", "Telecom",
    "Cash Equivalent", "Broad Market Index",
    # Chinese labels
    "必选消费", "医疗保健", "制药", "公用事业", "电信服务",
    "企业软件", "企业SaaS", "财税软件", "支付",
}

_CYCLICAL_SECTORS_FALLBACK = {
    "Semiconductors", "Technology Hardware", "Software",
    "Financials", "Energy", "Materials", "Industrial",
    "Consumer Discretionary", "Real Estate",
    # Chinese labels
    "半导体硬件", "半导体设备", "半导体IP", "半导体封测", "半导体测试",
    "通信设备", "光通信", "被动元件", "PCB/元器件",
    "新能源", "储能", "锂电材料", "机器人",
    "比特币挖矿", "房地产科技", "铀矿",
}

_GROWTH_SECTORS_FALLBACK = {
    "Communication Services", "Internet", "Media", "Information Technology",
    "Platform",
    # Chinese labels
    "通信服务", "互联网", "信息科技", "平台", "传媒",
}

DEFENSIVE_SECTORS = (
    set(_SECTORS_CFG.get("defensive")) if _SECTORS_CFG.get("defensive")
    else _DEFENSIVE_SECTORS_FALLBACK
)
CYCLICAL_SECTORS = (
    set(_SECTORS_CFG.get("cyclical")) if _SECTORS_CFG.get("cyclical")
    else _CYCLICAL_SECTORS_FALLBACK
)
GROWTH_SECTORS = (
    set(_SECTORS_CFG.get("growth")) if _SECTORS_CFG.get("growth")
    else _GROWTH_SECTORS_FALLBACK
)


# ══════════════════════════════════════════════════════════════════════════
# Scoring thresholds (verdict ladder / neutral / red lines) — 单一事实源
# 值逐字对齐 frame_const.yaml scoring.dong;config 缺失时回退硬编码(零行为变化)。
# ══════════════════════════════════════════════════════════════════════════

_DONG_CFG = _FRAME_CONST.get("scoring", {}).get("dong", {})

# 股东回报(分红+回购)加分配置 — 防御轨「现金流稳定性」维度内(§框架 v15)
# enabled:false 即回退原行为(零行为变化)。
_SHAREHOLDER_RETURN = _DONG_CFG.get("defensive", {}).get("shareholder_return") or {
    "enabled": True, "yield_min": 0.02, "bonus": 5,
}

_DEFENSIVE_TIERS = _DONG_CFG.get("defensive", {}).get("tiers") or [
    {"min": 80, "verdict": "优质底仓", "limit_pct": 15, "rhythm": "分3批，2-3周完成"},
    {"min": 60, "verdict": "合格底仓", "limit_pct": 10, "rhythm": "分2批，1-2周完成"},
    {"min": 40, "verdict": "观察级", "limit_pct": 5, "rhythm": "仅轻仓观察，不加仓"},
    {"min": 0, "verdict": "不符合防御标准", "limit_pct": 0, "rhythm": "不建仓，等待估值回落或现金流改善"},
]

_CYCLICAL_TIERS = _DONG_CFG.get("cyclical", {}).get("tiers") or [
    {"min": 70, "verdict": "优质周期机会", "limit_pct": 10, "constraint": "分批建仓，设定明确止盈位"},
    {"min": 50, "verdict": "可参与", "limit_pct": 5, "constraint": "仅小仓位波段，不长期持有"},
    {"min": 30, "verdict": "高风险", "limit_pct": 3, "constraint": "仅迷你仓观察"},
    {"min": 0, "verdict": "禁止参与", "limit_pct": 0, "constraint": "直接排除，不纳入自选"},
]

_DEFENSIVE_NEUTRAL = _DONG_CFG.get("neutral", {}).get("defensive") or {
    "生意刚需性": 13, "现金流稳定性": 15, "估值安全边际": 10,
    "资金逆向度": 8, "组合对冲价值": 5,
}

_CYCLICAL_NEUTRAL = _DONG_CFG.get("neutral", {}).get("cyclical") or {
    "景气周期阶段": 15, "估值水位": 13, "供给格局": 10,
    "防御仓覆盖": 8, "资金热度": 5,
}

_GROWTH_TIERS = _DONG_CFG.get("growth", {}).get("tiers") or [
    {"min": 75, "verdict": "优质成长", "limit_pct": 10, "constraint": "分批建仓，成长逻辑证伪即退"},
    {"min": 55, "verdict": "可参与", "limit_pct": 5, "constraint": "小仓位，跟踪营收/盈利增速是否兑现"},
    {"min": 35, "verdict": "高风险", "limit_pct": 3, "constraint": "仅迷你仓观察"},
    {"min": 0, "verdict": "禁止参与", "limit_pct": 0, "constraint": "直接排除，不纳入自选"},
]

_GROWTH_NEUTRAL = _DONG_CFG.get("neutral", {}).get("growth") or {
    "营收成长性": 12, "盈利成长性": 12, "盈利质量/护城河": 10,
    "现金流与财务健康": 7, "估值合理性": 7,
}

_RED_LINES = _DONG_CFG.get("red_lines") or {
    "negative_cashflow_years": 2,
    "avg_daily_volume_min": 5_000_000,
    "pe_percentile_high": 90,
    "single_stock_concentration_pct": 15,
    "debt_equity_max": 2.0,
    "short_pct_float_max": 20,
    "market_cap_min": 1_000_000_000,
    "revenue_growth_decline": -30,
}


def classify_holding(
    symbol: str,
    sector: str = "",
    known_classifications: Optional[dict[str, str]] = None,
) -> str:
    """Classify a holding as defensive, growth, cyclical, cash, or broad_index.

    Args:
        symbol: Ticker symbol (e.g. "AAPL", "6981.T", "9992.HK")
        sector: Sector/industry label (optional)
        known_classifications: Override map of symbol→classification

    Returns:
        One of: "defensive", "cyclical", "growth", "cash", "broad_index",
                "defensive_etf", or "unknown"
    """
    # Normalise symbol — strip market suffixes
    clean = symbol.upper()
    for suffix in (".T", ".HK", ".SH", ".SZ", ".L", ".SW"):
        clean = clean.replace(suffix, "")

    classifications = known_classifications or {}

    # Check known overrides first
    if clean in classifications:
        return classifications[clean]

    # Check sector membership
    if sector in DEFENSIVE_SECTORS:
        return "defensive"
    if sector in CYCLICAL_SECTORS:
        return "cyclical"
    if sector in GROWTH_SECTORS:
        return "growth"

    return "unknown"


# ══════════════════════════════════════════════════════════════════════════
# Defensive track (防御股)
# ══════════════════════════════════════════════════════════════════════════

def score_defensive(
    symbol: str,
    *,
    fundamentals: Optional[dict[str, Any]] = None,
    business_moat: int = 0,
    cashflow_stability: int = 0,
    valuation_safety: int = 0,
    capital_contrarian: int = 0,
    portfolio_hedge: int = 0,
    degrade_to_neutral: bool = False,
) -> dict[str, Any]:
    """Score a stock against the Dong Yiting defensive scoring framework.

    Five dimensions: business moat (25) + cashflow stability (30) +
    valuation safety (20) + capital contrarian (15) + portfolio hedge (10) = 100.

    Each dimension can be explicitly provided (override) or derived from
    ``fundamentals`` dict.  When neither is available and degrade_to_neutral
    is True, the dimension receives a neutral mid-range score.

    Args:
        symbol: Ticker symbol
        fundamentals: Pre-fetched fundamental data dict.  Expected keys:
            sector, pe, fcf_yield, debt_equity, short_pct_float
        business_moat: Explicit score for 生意刚需性 (0-25)
        cashflow_stability: Explicit score for 现金流稳定性 (0-30)
        valuation_safety: Explicit score for 估值安全边际 (0-20)
        capital_contrarian: Explicit score for 资金逆向度 (0-15)
        portfolio_hedge: Explicit score for 组合对冲价值 (0-10)
        degrade_to_neutral: If True, missing dimensions get neutral score
                           instead of 0 (used during data outages)

    Returns:
        {
            symbol, track: "defensive", total (0-100), max_score: 100,
            verdict, position_limit_pct, build_rhythm,
            dimensions: {label: score, ...},
            generated_at: ISO timestamp,
            degraded: bool (True if any dimension fell back to neutral)
        }
    """
    fund = fundamentals or {}
    dims: dict[str, int] = {}
    degraded = False
    NEUTRAL = _DEFENSIVE_NEUTRAL

    # ── Dimension 1: Business Moat (25 points) ──
    if business_moat > 0:
        dims["生意刚需性"] = min(business_moat, 25)
    elif fund:
        sector = fund.get("sector", "")
        if sector in ("必选消费", "医疗保健", "公用事业"):
            dims["生意刚需性"] = 22
        elif sector in ("企业软件", "企业SaaS", "支付", "电信"):
            dims["生意刚需性"] = 18
        elif sector in ("消费电子", "餐饮", "娱乐"):
            dims["生意刚需性"] = 12
        elif "半导体" in str(sector) or "通信" in str(sector):
            dims["生意刚需性"] = 10
        else:
            dims["生意刚需性"] = 8
    elif degrade_to_neutral:
        dims["生意刚需性"] = NEUTRAL["生意刚需性"]
        degraded = True
    else:
        dims["生意刚需性"] = 0

    # ── Dimension 2: Cashflow Stability (30 points) ──
    if cashflow_stability > 0:
        dims["现金流稳定性"] = min(cashflow_stability, 30)
    elif fund:
        fcf_y = fund.get("fcf_yield")
        de = fund.get("debt_equity")
        score = 15
        if fcf_y is not None and fcf_y > 0.03:
            score += 10
        elif fcf_y is not None and fcf_y > 0:
            score += 5
        if de is not None and de < 1.0:
            score += 5
        if fcf_y is not None and fcf_y < 0:
            score -= 10
        # 股东回报(分红+回购)加分 — 防御股核心吸引力之一(§框架 v15)
        if _SHAREHOLDER_RETURN.get("enabled", True):
            sy = (fund.get("dividend_yield") or 0) + (fund.get("buyback_yield") or 0)
            if sy >= _SHAREHOLDER_RETURN.get("yield_min", 0.02):
                score += _SHAREHOLDER_RETURN.get("bonus", 5)
        dims["现金流稳定性"] = max(0, min(30, score))
    elif degrade_to_neutral:
        dims["现金流稳定性"] = NEUTRAL["现金流稳定性"]
        degraded = True
    else:
        dims["现金流稳定性"] = 0

    # ── Dimension 3: Valuation Safety (20 points) ──
    if valuation_safety > 0:
        dims["估值安全边际"] = min(valuation_safety, 20)
    elif fund:
        pe = fund.get("pe")
        if pe is not None and pe < 0:
            dims["估值安全边际"] = 0
        elif pe is not None and pe < 15:
            dims["估值安全边际"] = 20
        elif pe is not None and pe < 25:
            dims["估值安全边际"] = 15
        elif pe is not None and pe < 35:
            dims["估值安全边际"] = 8
        elif pe is not None and pe < 50:
            dims["估值安全边际"] = 3
        else:
            dims["估值安全边际"] = 0
    elif degrade_to_neutral:
        dims["估值安全边际"] = NEUTRAL["估值安全边际"]
        degraded = True
    else:
        dims["估值安全边际"] = 0

    # ── Dimension 4: Capital Contrarian (15 points) ──
    if capital_contrarian > 0:
        dims["资金逆向度"] = min(capital_contrarian, 15)
    elif fund:
        short_pct = fund.get("short_pct_float")
        score = 8
        if short_pct is not None:
            pct = short_pct * 100 if short_pct < 1 else short_pct
            if pct > 10:
                score += 5  # high short interest = contrarian opportunity
            elif pct < 3:
                score -= 3  # low short interest = no contrarian edge
        dims["资金逆向度"] = max(0, min(15, score))
    elif degrade_to_neutral:
        dims["资金逆向度"] = NEUTRAL["资金逆向度"]
        degraded = True
    else:
        dims["资金逆向度"] = 0

    # ── Dimension 5: Portfolio Hedge Value (10 points) ──
    if portfolio_hedge > 0:
        dims["组合对冲价值"] = min(portfolio_hedge, 10)
    elif degrade_to_neutral:
        dims["组合对冲价值"] = NEUTRAL["组合对冲价值"]
        degraded = True
    else:
        dims["组合对冲价值"] = 5  # default neutral

    total = sum(dims.values())

    # ── Verdict ──
    verdict, limit_pct, rhythm = "不符合防御标准", 0, "不建仓，等待估值回落或现金流改善"
    for tier in sorted(_DEFENSIVE_TIERS, key=lambda t: t.get("min", 0), reverse=True):
        if total >= tier.get("min", 0):
            verdict = tier.get("verdict", verdict)
            limit_pct = tier.get("limit_pct", 0)
            rhythm = tier.get("rhythm", "")
            break

    from datetime import datetime, timezone, timedelta
    return {
        "symbol": symbol,
        "track": "defensive",
        "total": max(0, min(100, total)),
        "max_score": 100,
        "verdict": verdict,
        "position_limit_pct": limit_pct,
        "build_rhythm": rhythm,
        "dimensions": dims,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "degraded": degraded,
        "missing_dimensions": [
            k for k, v in dims.items()
            if v == NEUTRAL.get(k, 0) and degrade_to_neutral
        ] if degraded else [],
    }


# ══════════════════════════════════════════════════════════════════════════
# Cyclical track (周期股)
# ══════════════════════════════════════════════════════════════════════════

def score_cyclical(
    symbol: str,
    *,
    fundamentals: Optional[dict[str, Any]] = None,
    cycle_stage: int = 0,
    valuation_watermark: int = 0,
    supply_structure: int = 0,
    defense_coverage: int = 0,
    capital_heat: int = 0,
    degrade_to_neutral: bool = False,
) -> dict[str, Any]:
    """Score a stock against the Dong Yiting cyclical scoring framework.

    Five dimensions: cycle stage (30) + valuation watermark (25) +
    supply structure (20) + defense coverage (15) + capital heat (10) = 100.

    Args:
        symbol: Ticker symbol
        fundamentals: Pre-fetched fundamental data dict.  Expected keys:
            revenue_growth, earnings_growth, pe
        cycle_stage: Explicit score for 景气周期阶段 (0-30)
        valuation_watermark: Explicit score for 估值水位 (0-25)
        supply_structure: Explicit score for 供给格局 (0-20)
        defense_coverage: Explicit score for 防御仓覆盖 (0-15)
        capital_heat: Explicit score for 资金热度 (0-10)
        degrade_to_neutral: If True, missing dimensions get neutral score

    Returns:
        {symbol, track: "cyclical", total, verdict, position_limit_pct, ...}
    """
    fund = fundamentals or {}
    dims: dict[str, int] = {}
    degraded = False
    NEUTRAL = _CYCLICAL_NEUTRAL

    # ── Dimension 1: Cycle Stage (30 points) ──
    # High score = late cycle / downturn (better entry for cyclical)
    # Low score = peak cycle (danger zone)
    if cycle_stage > 0:
        dims["景气周期阶段"] = min(cycle_stage, 30)
    elif fund:
        rev_g = fund.get("revenue_growth")
        earn_g = fund.get("earnings_growth")
        score = 15
        if rev_g is not None:
            if rev_g > 20:
                score = 10  # peak growth → late cycle
            elif rev_g < -5:
                score = 20  # contraction → early recovery
        if earn_g is not None and earn_g < -30:
            score = max(score, 25)  # deep earnings trough
        dims["景气周期阶段"] = max(0, min(30, score))
    elif degrade_to_neutral:
        dims["景气周期阶段"] = NEUTRAL["景气周期阶段"]
        degraded = True
    else:
        dims["景气周期阶段"] = 0

    # ── Dimension 2: Valuation Watermark (25 points) ──
    # High score = cheap (good), low score = expensive (bad)
    if valuation_watermark > 0:
        dims["估值水位"] = min(valuation_watermark, 25)
    elif fund:
        pe = fund.get("pe")
        if pe is not None and pe < 0:
            dims["估值水位"] = 5  # unprofitable — uncertain
        elif pe is not None and pe < 12:
            dims["估值水位"] = 25  # very cheap
        elif pe is not None and pe < 20:
            dims["估值水位"] = 15
        elif pe is not None and pe < 35:
            dims["估值水位"] = 5
        else:
            dims["估值水位"] = 0  # extremely expensive
    elif degrade_to_neutral:
        dims["估值水位"] = NEUTRAL["估值水位"]
        degraded = True
    else:
        dims["估值水位"] = 0

    # ── Dimension 3: Supply Structure (20 points) ──
    if supply_structure > 0:
        dims["供给格局"] = min(supply_structure, 20)
    elif degrade_to_neutral:
        dims["供给格局"] = NEUTRAL["供给格局"]
        degraded = True
    else:
        dims["供给格局"] = 10  # neutral default

    # ── Dimension 4: Defense Coverage (15 points) ──
    if defense_coverage > 0:
        dims["防御仓覆盖"] = min(defense_coverage, 15)
    elif degrade_to_neutral:
        dims["防御仓覆盖"] = NEUTRAL["防御仓覆盖"]
        degraded = True
    else:
        dims["防御仓覆盖"] = 0

    # ── Dimension 5: Capital Heat (10 points) ──
    # High = oversold/contrarian, low = overheated/herding
    if capital_heat > 0:
        dims["资金热度"] = min(capital_heat, 10)
    elif degrade_to_neutral:
        dims["资金热度"] = NEUTRAL["资金热度"]
        degraded = True
    else:
        dims["资金热度"] = 5  # neutral default

    total = sum(dims.values())

    # ── Verdict ──
    verdict, limit_pct, constraint = "禁止参与", 0, "直接排除，不纳入自选"
    for tier in sorted(_CYCLICAL_TIERS, key=lambda t: t.get("min", 0), reverse=True):
        if total >= tier.get("min", 0):
            verdict = tier.get("verdict", verdict)
            limit_pct = tier.get("limit_pct", 0)
            constraint = tier.get("constraint", "")
            break

    from datetime import datetime, timezone, timedelta
    return {
        "symbol": symbol,
        "track": "cyclical",
        "total": max(0, min(100, total)),
        "max_score": 100,
        "verdict": verdict,
        "position_limit_pct": limit_pct,
        "constraint": constraint,
        "dimensions": dims,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "degraded": degraded,
        "missing_dimensions": [
            k for k, v in dims.items()
            if v == NEUTRAL.get(k, 0) and degrade_to_neutral
        ] if degraded else [],
    }


# ══════════════════════════════════════════════════════════════════════════
# Growth track (成长股)
# ══════════════════════════════════════════════════════════════════════════

def score_growth(
    symbol: str,
    *,
    fundamentals: Optional[dict[str, Any]] = None,
    revenue_growth: int = 0,
    earnings_growth: int = 0,
    margin_quality: int = 0,
    cashflow_health: int = 0,
    valuation_reasonableness: int = 0,
    degrade_to_neutral: bool = False,
) -> dict[str, Any]:
    """Score a stock against the growth scoring framework.

    Five dimensions: revenue growth (25) + earnings growth (25) +
    margin quality/moat (20) + cashflow & financial health (15) +
    valuation reasonableness (15) = 100.

    Units (与 fundamental cache 约定一致):
      - revenue_growth / earnings_growth: PERCENT (20.05 = 20.05%)
      - gross_margins / operating_margins: FRACTION (0.609 = 60.9%)
      - roe: PERCENT (50.84)
      - fcf_yield: FRACTION (0.0152)
      - debt_equity: RATIO (0.1229)
      - pe: number (17.31)

    Args:
        symbol: Ticker symbol
        fundamentals: Pre-fetched fundamental data dict.  Expected keys:
            revenue_growth, earnings_growth, gross_margins, operating_margins,
            roe, fcf_yield, debt_equity, pe
        revenue_growth: Explicit override for 营收成长性 (0-25)
        earnings_growth: Explicit override for 盈利成长性 (0-25)
        margin_quality: Explicit override for 盈利质量/护城河 (0-20)
        cashflow_health: Explicit override for 现金流与财务健康 (0-15)
        valuation_reasonableness: Explicit override for 估值合理性 (0-15)
        degrade_to_neutral: If True, missing dimensions get neutral score

    Returns:
        {symbol, track: "growth", total, verdict, position_limit_pct,
         constraint, dimensions, note (PEG 附注), generated_at, degraded,
         missing_dimensions}
    """
    fund = fundamentals or {}
    dims: dict[str, int] = {}
    degraded = False
    NEUTRAL = _GROWTH_NEUTRAL

    def _growth_band(g: float) -> int:
        """营收/盈利增速阶梯(percent): ≥25→25 / 20-25→20 / 15-20→15 / 10-15→10 / 5-10→5 / <5→0."""
        if g >= 25:
            return 25
        if g >= 20:
            return 20
        if g >= 15:
            return 15
        if g >= 10:
            return 10
        if g >= 5:
            return 5
        return 0

    # ── Dimension 1: Revenue Growth (25 points) ──
    if revenue_growth > 0:
        dims["营收成长性"] = min(revenue_growth, 25)
    elif fund and fund.get("revenue_growth") is not None:
        dims["营收成长性"] = _growth_band(float(fund["revenue_growth"]))
    elif degrade_to_neutral:
        dims["营收成长性"] = NEUTRAL["营收成长性"]
        degraded = True
    else:
        dims["营收成长性"] = 0

    # ── Dimension 2: Earnings Growth (25 points, truncated ≤40%) ──
    if earnings_growth > 0:
        dims["盈利成长性"] = min(earnings_growth, 25)
    elif fund and fund.get("earnings_growth") is not None:
        g = min(float(fund["earnings_growth"]), 40.0)  # 截断 ≤40%,避免一次性基数效应
        dims["盈利成长性"] = _growth_band(g)
    elif degrade_to_neutral:
        dims["盈利成长性"] = NEUTRAL["盈利成长性"]
        degraded = True
    else:
        dims["盈利成长性"] = 0

    # ── Dimension 3: Margin Quality / Moat (20 points) ──
    if margin_quality > 0:
        dims["盈利质量/护城河"] = min(margin_quality, 20)
    elif fund:
        score = 0
        gm = fund.get("gross_margins")
        om = fund.get("operating_margins")
        roe = fund.get("roe")
        if gm is not None and gm >= 0.40:
            score += 5
        if om is not None and om >= 0.20:
            score += 5
        if roe is not None and roe >= 20:
            score += 10
        dims["盈利质量/护城河"] = max(0, min(20, score))
    elif degrade_to_neutral:
        dims["盈利质量/护城河"] = NEUTRAL["盈利质量/护城河"]
        degraded = True
    else:
        dims["盈利质量/护城河"] = 0

    # ── Dimension 4: Cashflow & Financial Health (15 points) ──
    if cashflow_health > 0:
        dims["现金流与财务健康"] = min(cashflow_health, 15)
    elif fund:
        score = 0
        fcf = fund.get("fcf_yield")
        de = fund.get("debt_equity")
        if fcf is not None and fcf > 0:
            score += 5
        if de is not None and de < 0.5:
            score += 10
        dims["现金流与财务健康"] = max(0, min(15, score))
    elif degrade_to_neutral:
        dims["现金流与财务健康"] = NEUTRAL["现金流与财务健康"]
        degraded = True
    else:
        dims["现金流与财务健康"] = 0

    # ── Dimension 5: Valuation Reasonableness (15 points) ──
    if valuation_reasonableness > 0:
        dims["估值合理性"] = min(valuation_reasonableness, 15)
    elif fund:
        pe = fund.get("pe")
        if pe is not None and pe < 0:
            dims["估值合理性"] = 0  # 亏损:估值维度零分
        elif pe is not None and pe < 20:
            dims["估值合理性"] = 15
        elif pe is not None and pe < 30:
            dims["估值合理性"] = 10
        elif pe is not None and pe < 45:
            dims["估值合理性"] = 5
        else:
            dims["估值合理性"] = 0  # 极度昂贵
    elif degrade_to_neutral:
        dims["估值合理性"] = NEUTRAL["估值合理性"]
        degraded = True
    else:
        dims["估值合理性"] = 0

    total = sum(dims.values())

    # ── Verdict ──
    verdict, limit_pct, constraint = "禁止参与", 0, "直接排除，不纳入自选"
    for tier in sorted(_GROWTH_TIERS, key=lambda t: t.get("min", 0), reverse=True):
        if total >= tier.get("min", 0):
            verdict = tier.get("verdict", verdict)
            limit_pct = tier.get("limit_pct", 0)
            constraint = tier.get("constraint", "")
            break

    from datetime import datetime, timezone, timedelta

    # ── PEG 附注(首版用 trailing PE;forward PE 需一致预期,缓存无) ──
    pe = fund.get("pe")
    eg = fund.get("earnings_growth")
    note = ""
    if pe is not None and eg is not None:
        growth_rate = max(min(float(eg), 40.0), 5.0)
        peg = float(pe) / growth_rate
        note = f"trailing PE {float(pe):.1f} / 成长率 {growth_rate:.0f}% → PEG {peg:.2f}（无 forward 一致预期）"

    return {
        "symbol": symbol,
        "track": "growth",
        "total": max(0, min(100, total)),
        "max_score": 100,
        "verdict": verdict,
        "position_limit_pct": limit_pct,
        "constraint": constraint,
        "dimensions": dims,
        "note": note,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "degraded": degraded,
        "missing_dimensions": [
            k for k, v in dims.items()
            if v == NEUTRAL.get(k, 0) and degrade_to_neutral
        ] if degraded else [],
    }


# ══════════════════════════════════════════════════════════════════════════
# Auto-classify + score
# ══════════════════════════════════════════════════════════════════════════

def score_holding(
    symbol: str,
    holding_type: str = "",
    market: str = "US",
    *,
    fundamentals: Optional[dict[str, Any]] = None,
    known_classifications: Optional[dict[str, str]] = None,
    **overrides,
) -> dict[str, Any]:
    """Auto-classify and score a holding using the appropriate track.

    Args:
        symbol: Ticker symbol
        holding_type: Pre-classified type.  If empty, auto-classified.
        market: Market code ("US", "HK", "JP", "A")
        fundamentals: Pre-fetched fundamental data dict
        known_classifications: Override map for classify_holding()
        **overrides: Passed through to score_defensive() or score_cyclical()

    Returns:
        Score dict from score_defensive() or score_cyclical(), or a special
        pass-through dict for cash/broad_index/defensive_etf.
    """
    fund = fundamentals or {}
    sector = fund.get("sector", "")

    if not holding_type:
        holding_type = classify_holding(symbol, sector, known_classifications)

    # Cash and broad indices auto-pass
    if holding_type in ("cash", "broad_index", "defensive_etf"):
        from datetime import datetime, timezone, timedelta
        return {
            "symbol": symbol,
            "track": holding_type,
            "total": 100,
            "verdict": "自动通过",
            "position_limit_pct": 100 if holding_type == "cash" else 20,
            "dimensions": {},
            "note": "现金/宽基ETF自动通过，无需打分",
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "degraded": False,
            "missing_dimensions": [],
        }

    if holding_type == "defensive":
        return score_defensive(symbol, fundamentals=fund, **overrides)
    elif holding_type == "growth":
        return score_growth(symbol, fundamentals=fund, **overrides)
    else:
        return score_cyclical(symbol, fundamentals=fund, **overrides)


# ══════════════════════════════════════════════════════════════════════════
# Red-line screening (§3.3)
# ══════════════════════════════════════════════════════════════════════════

def check_red_lines(
    symbol: str,
    *,
    avg_daily_volume: Optional[float] = None,
    pe_percentile: Optional[float] = None,
    negative_cashflow_years: int = 0,
    single_stock_concentration_pct: Optional[float] = None,
    debt_equity: Optional[float] = None,
    short_pct_float: Optional[float] = None,
    market_cap: Optional[float] = None,
    revenue_growth: Optional[float] = None,
) -> list[dict[str, str]]:
    """Run the 8-item red-line screening against one stock.

    Each red line is a hard constraint.  Triggering ANY red line means the
    stock should not be bought (or should be sold if already held).

    Red lines:
      1. 连续经营现金流为负 ≥ 2年
      2. 日均成交额 < 500万 (liquidity trap)
      3. PE处于5年 > 90%分位 (valuation extreme)
      4. 单票集中度 > 15% (position limit — portfolio-level)
      5. 净负债率 > 200% (extreme leverage)
      6. 空头占比 > 20% (crowded short — borrow cost risk)
      7. 中小盘市值 < 10亿 (micro-cap risk)
      8. 营收连续下降 ≥ 3年 (terminal decline)

    Returns:
        List of triggered red-line checks.  Empty list = all passed.
    """
    triggers: list[dict[str, str]] = []
    rl = _RED_LINES

    # Red line 1: Negative operating cashflow ≥ 2 years
    if negative_cashflow_years >= rl.get("negative_cashflow_years", 2):
        triggers.append({
            "check": "negative_cashflow",
            "detail": f"近3年经营现金流有{negative_cashflow_years}年为负",
        })

    # Red line 2: Average daily volume < ¥5M
    if avg_daily_volume is not None and avg_daily_volume < rl.get("avg_daily_volume_min", 5_000_000):
        triggers.append({
            "check": "low_liquidity",
            "detail": f"日均成交额 ¥{avg_daily_volume:,.0f} < ¥500万",
        })

    # Red line 3: PE at > 90th percentile of 5-year range
    if pe_percentile is not None and pe_percentile > rl.get("pe_percentile_high", 90):
        triggers.append({
            "check": "pe_extreme",
            "detail": f"PE处于5年{pe_percentile:.0f}%分位",
        })

    # Red line 4: Single-stock concentration > 15%
    if single_stock_concentration_pct is not None and single_stock_concentration_pct > rl.get("single_stock_concentration_pct", 15):
        triggers.append({
            "check": "concentration",
            "detail": f"单票集中度 {single_stock_concentration_pct:.1f}% > 15% 上限",
        })

    # Red line 5: D/E > 2.0 (extreme leverage)
    if debt_equity is not None and debt_equity > rl.get("debt_equity_max", 2.0):
        triggers.append({
            "check": "extreme_leverage",
            "detail": f"净负债率 D/E={debt_equity:.1f} > 2.0",
        })

    # Red line 6: Short float > 20%
    if short_pct_float is not None:
        pct = short_pct_float * 100 if short_pct_float < 1 else short_pct_float
        if pct > rl.get("short_pct_float_max", 20):
            triggers.append({
                "check": "high_short_interest",
                "detail": f"空头占比 {pct:.1f}% > 20%",
            })

    # Red line 7: Market cap < ¥1B (micro-cap)
    if market_cap is not None and market_cap < rl.get("market_cap_min", 1_000_000_000):
        triggers.append({
            "check": "micro_cap",
            "detail": f"市值 ¥{market_cap:,.0f} < ¥10亿",
        })

    # Red line 8: Revenue declining ≥ 3 consecutive years
    if revenue_growth is not None and revenue_growth < rl.get("revenue_growth_decline", -30):
        triggers.append({
            "check": "terminal_decline",
            "detail": f"营收增速 {revenue_growth:.1f}% — 可能处于持续性衰退",
        })

    return triggers
