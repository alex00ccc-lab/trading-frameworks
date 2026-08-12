"""Three-framework serial pipeline (三框架串联调度).

Execution flow (not a weighted overlay):

  段永平 (能不能买, ≥60) → 马克斯 (什么时候买, ≥50) → 董艺婷 (买多少/怎么管)

Modes:
  - "all":    全部三关串联（默认）
  - "duan":   仅段永平门槛
  - "marks":  仅马克斯周期判断
  - "dong":   仅董艺婷执行层
  - "duan+dong": 段永平 + 董艺婷（跳过马克斯）
  - "common": 仅三框架交集规则（极简严格风控）

All functions are PURE: no IO, no CLI, no logger.  Callers provide
pre-fetched data and framework-specific parameters.
"""

from __future__ import annotations

from typing import Any, Optional, Literal

from duan_yongping.scoring.duan_score import score_duan
from howard_marks.scoring.marks_score import score_marks
from dong_yiting.scoring.dual_track import score_holding, check_red_lines, classify_holding


ModeStr = Literal["all", "duan", "marks", "dong", "duan+dong", "common"]


# ══════════════════════════════════════════════════════════════════════════
# Common rules — intersection of all three frameworks
# ══════════════════════════════════════════════════════════════════════════

COMMON_RULES = [
    "thesis_required",           # 必须写 Thesis
    "circle_of_competence",      # 不懂不投
    "margin_of_safety",          # 有安全边际
    "position_sizing",           # 仓位控制
    "stop_loss",                 # 必须有止损
]


def check_common_rules(
    thesis_provided: bool = False,
    in_circle_of_competence: bool = False,
    has_margin_of_safety: bool = False,
    position_within_limits: bool = False,
    stop_loss_set: bool = False,
) -> dict[str, Any]:
    """Check the five common rules shared by all three frameworks.

    These are the NON-NEGOTIABLE rules.  Any failure = block.
    """
    checks = {
        "thesis_required":         thesis_provided,
        "circle_of_competence":    in_circle_of_competence,
        "margin_of_safety":        has_margin_of_safety,
        "position_sizing":         position_within_limits,
        "stop_loss":               stop_loss_set,
    }
    failed = [rule for rule, ok in checks.items() if not ok]
    return {
        "all_passed": len(failed) == 0,
        "failed": failed,
        "checks": checks,
    }


# ══════════════════════════════════════════════════════════════════════════
# Serial pipeline
# ══════════════════════════════════════════════════════════════════════════

def run_master_pipeline(
    symbol: str,
    market: str = "US",
    mode: str = "all",
    *,
    # Common rule inputs
    thesis_provided: bool = False,
    in_circle_of_competence: bool = False,
    has_margin_of_safety: bool = False,
    position_within_limits: bool = False,
    stop_loss_set: bool = False,
    # Duan params
    duan_params: Optional[dict[str, Any]] = None,
    # Marks params
    marks_params: Optional[dict[str, Any]] = None,
    # Dong params
    dong_params: Optional[dict[str, Any]] = None,
    dong_fundamentals: Optional[dict[str, Any]] = None,
    dong_holding_type: str = "",
    dong_known_classifications: Optional[dict[str, str]] = None,
    dong_red_line_params: Optional[dict[str, Any]] = None,
    # Degradation
    degrade_to_neutral: bool = False,
) -> dict[str, Any]:
    """Run the three-framework serial pipeline for a buy/sell decision.

    Pipeline logic (mode="all"):
      1. 段永平: score ≥ 60?  NO → BLOCKED
      2. 马克斯: score ≥ 50?  NO → YELLOW (wait, not blocked)
      3. 董艺婷: position limit / stop loss / build rhythm

    When mode is "common", only the 5 common rules are checked.

    Args:
        symbol: Ticker symbol
        market: Market code ("US", "HK", "JP", "A")
        mode: "all" | "duan" | "marks" | "dong" | "duan+dong" | "common"
        degrade_to_neutral: Propagate to all scoring functions

    Returns:
        {
            symbol, market, mode,
            pipeline_passed: bool (clean through all gates),
            blocked: bool (hard block — do not buy),
            blocked_by: ["段永平"] | [] (which gate blocked),
            warnings: ["马克斯"] | [],
            scores: {duan: {...}, marks: {...}, dong: {...}},
            common_rules: {...},
            checklist: {...},        # actionable: limit_pct, stop_loss_pct, ...
            generated_at: ISO,
        }
    """
    duan_p = duan_params or {}
    marks_p = marks_params or {}
    dong_p = dong_params or {}
    dong_rl = dong_red_line_params or {}

    blocked: list[str] = []
    warnings: list[str] = []
    scores: dict[str, Any] = {}

    # ── Gate 1: Common Rules (always checked) ──
    common = check_common_rules(
        thesis_provided, in_circle_of_competence,
        has_margin_of_safety, position_within_limits, stop_loss_set,
    )

    if mode == "common":
        return {
            "symbol": symbol,
            "market": market,
            "mode": "common",
            "pipeline_passed": common["all_passed"],
            "blocked": not common["all_passed"],
            "blocked_by": common["failed"],
            "warnings": [],
            "scores": {},
            "common_rules": common,
            "checklist": _build_checklist(None, None, None, common),
            "generated_at": _now_iso(),
        }

    # ── Gate 2: 段永平 (能不能买) ──
    if mode in ("all", "duan", "duan+dong"):
        duan_result = score_duan(
            symbol,
            fundamentals=duan_p.get("fundamentals"),
            competence_level=duan_p.get("competence_level", "YELLOW"),
            obsidian_note_words=duan_p.get("obsidian_note_words", 0),
            trade_count=duan_p.get("trade_count", 0),
            sector_familiarity=duan_p.get("sector_familiarity", 0.5),
            pe=duan_p.get("pe"),
            pe_percentile_5y=duan_p.get("pe_percentile_5y"),
            fcf_yield=duan_p.get("fcf_yield"),
            discount_to_intrinsic_pct=duan_p.get("discount_to_intrinsic_pct"),
            roic=duan_p.get("roic"),
            gross_margin=duan_p.get("gross_margin"),
            roe=duan_p.get("roe"),
            revenue_growth_3y_avg=duan_p.get("revenue_growth_3y_avg"),
            debt_equity=duan_p.get("debt_equity"),
            degrade_to_neutral=degrade_to_neutral,
        )
        scores["duan"] = duan_result
        if not duan_result["passed"]:
            blocked.append("段永平")

    # ── Gate 3: 马克斯 (什么时候买) ──
    if mode in ("all", "marks"):
        marks_result = score_marks(
            symbol,
            fundamentals=marks_p.get("fundamentals"),
            pe_percentile_5y=marks_p.get("pe_percentile_5y"),
            sector_momentum_30d=marks_p.get("sector_momentum_30d"),
            vix=marks_p.get("vix"),
            credit_spread=marks_p.get("credit_spread"),
            fed_rate_direction=marks_p.get("fed_rate_direction", "neutral"),
            sector_etf_flow_30d=marks_p.get("sector_etf_flow_30d"),
            short_pct_float=marks_p.get("short_pct_float"),
            analyst_consensus=marks_p.get("analyst_consensus", "hold"),
            price_vs_200ma_pct=marks_p.get("price_vs_200ma_pct"),
            insider_trend=marks_p.get("insider_trend", "neutral"),
            equity_risk_premium=marks_p.get("equity_risk_premium"),
            earnings_yield=marks_p.get("earnings_yield"),
            ten_year_yield=marks_p.get("ten_year_yield"),
            shiller_pe_percentile=marks_p.get("shiller_pe_percentile"),
            degrade_to_neutral=degrade_to_neutral,
        )
        scores["marks"] = marks_result
        if not marks_result["passed"]:
            warnings.append("马克斯")  # Warning, not hard block

    # ── Gate 4: 董艺婷 (买多少 / 怎么管) ──
    if mode in ("all", "dong", "duan+dong"):
        dong_result = score_holding(
            symbol,
            holding_type=dong_holding_type,
            market=market,
            fundamentals=dong_fundamentals,
            known_classifications=dong_known_classifications,
            **{k: v for k, v in dong_p.items()
               if k in ("business_moat", "cashflow_stability", "valuation_safety",
                        "capital_contrarian", "portfolio_hedge",
                        "cycle_stage", "valuation_watermark", "supply_structure",
                        "defense_coverage", "capital_heat",
                        "degrade_to_neutral")},
        )
        if degrade_to_neutral:
            dong_result["degrade_to_neutral"] = True

        # Red-line screening
        red_lines = check_red_lines(
            symbol,
            avg_daily_volume=dong_rl.get("avg_daily_volume"),
            pe_percentile=dong_rl.get("pe_percentile"),
            negative_cashflow_years=dong_rl.get("negative_cashflow_years", 0),
            single_stock_concentration_pct=dong_rl.get("single_stock_concentration_pct"),
            debt_equity=dong_rl.get("debt_equity"),
            short_pct_float=dong_rl.get("short_pct_float"),
            market_cap=dong_rl.get("market_cap"),
            revenue_growth=dong_rl.get("revenue_growth"),
        )
        dong_result["red_lines"] = red_lines
        dong_result["red_lines_triggered"] = len(red_lines)

        scores["dong"] = dong_result

        if red_lines:
            blocked.append("董艺婷红线")

    # ── Assemble result ──
    blocked_final = len(blocked) > 0
    pipeline_passed = not blocked_final

    return {
        "symbol": symbol,
        "market": market,
        "mode": mode,
        "pipeline_passed": pipeline_passed,
        "blocked": blocked_final,
        "blocked_by": blocked,
        "warnings": warnings,
        "scores": scores,
        "common_rules": common,
        "checklist": _build_checklist(
            scores.get("duan"), scores.get("marks"), scores.get("dong"), common),
        "generated_at": _now_iso(),
    }


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════

def _build_checklist(
    duan: Optional[dict],
    marks: Optional[dict],
    dong: Optional[dict],
    common: dict,
) -> dict[str, Any]:
    """Build an actionable checklist from pipeline results."""
    checklist: dict[str, Any] = {
        "can_buy": True,
        "position_limit_pct": 0,
        "stop_loss_pct": 8,  # default
        "build_rhythm": "未知",
        "hard_constraints": [],
    }

    # Dong result has the most granular position guidance
    if dong:
        checklist["position_limit_pct"] = dong.get("position_limit_pct", 0)
        checklist["build_rhythm"] = dong.get("build_rhythm") or dong.get("constraint", "")
        if dong.get("red_lines_triggered", 0) > 0:
            checklist["can_buy"] = False
            checklist["hard_constraints"].append(
                f"触发{dong['red_lines_triggered']}条红线")
        if dong.get("total", 100) < 40:
            checklist["can_buy"] = False

    # Duan provides the threshold gate
    if duan and not duan.get("passed"):
        checklist["can_buy"] = False
        checklist["hard_constraints"].append("段永平框架未通过(≥60)")

    # Marks provides timing warning
    if marks:
        checklist["cycle_label"] = marks.get("cycle_label", "")
        if marks.get("total", 100) < 30:
            checklist["hard_constraints"].append("马克斯周期极差(≤30)")

    # Common rules
    if common.get("failed"):
        checklist["can_buy"] = False
        for rule in common["failed"]:
            checklist["hard_constraints"].append(f"通用规则未通过: {rule}")

    return checklist


def _now_iso() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat()
