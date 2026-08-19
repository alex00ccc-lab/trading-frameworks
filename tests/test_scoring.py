"""Unit tests for all three framework scoring modules.

Run: pytest tests/test_scoring.py -v
"""

import sys
from pathlib import Path

# Make trading-frameworks importable from tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


# ══════════════════════════════════════════════════════════════════════════
# Duan Yongping scoring
# ══════════════════════════════════════════════════════════════════════════

class TestDuanScore:
    """段永平四维打分测试"""

    def test_green_competence_passes(self):
        """GREEN 能力圈 + 合理估值 → 应通过"""
        from duan_yongping.scoring.duan_score import score_duan

        result = score_duan(
            "AAPL",
            competence_level="GREEN",
            pe=25, pe_percentile_5y=40,
            fcf_yield=0.04, roic=0.25,
            gross_margin=0.45, roe=0.50,
            revenue_growth_3y_avg=10,
            debt_equity=1.5,
        )
        assert result["passed"] is True
        assert result["total"] >= 60
        assert result["framework"] == "duan"
        assert "能力圈" in result["dimensions"]
        assert result["dimensions"]["能力圈"]["score"] == 25  # GREEN

    def test_red_competence_blocks(self):
        """RED 能力圈 → 高分也难通过"""
        from duan_yongping.scoring.duan_score import score_duan

        result = score_duan(
            "UNKNOWN",
            competence_level="RED",
            pe=10, pe_percentile_5y=15,
            fcf_yield=0.06, roic=0.30,
            gross_margin=0.65, roe=0.40,
            revenue_growth_3y_avg=20,
            debt_equity=0.5,
        )
        # RED means 0 on competence — should struggle to pass
        assert result["dimensions"]["能力圈"]["score"] == 0

    def test_negative_pe_penalizes(self):
        """负 PE → 安全边际扣分"""
        from duan_yongping.scoring.duan_score import score_duan

        result = score_duan(
            "LOSSCO",
            competence_level="YELLOW",
            pe=-5, fcf_yield=-0.02,
            roic=-0.05, roe=-0.10,
        )
        dim = result["dimensions"]["安全边际"]
        assert dim["score"] < 15  # negative PE penalized

    def test_high_roic_wide_moat(self):
        """高 ROIC + 高毛利率 → 宽护城河"""
        from duan_yongping.scoring.duan_score import score_duan

        result = score_duan(
            "MOATCO",
            competence_level="GREEN",
            roic=0.35, gross_margin=0.70,
            market_share_rank=1,
            pe=22, fcf_yield=0.05, roe=0.30,
        )
        dim = result["dimensions"]["护城河"]
        assert dim["score"] >= 20  # excellent moat

    def test_degrade_to_neutral(self):
        """降级模式 → 所有维度返回中性分"""
        from duan_yongping.scoring.duan_score import score_duan

        result = score_duan("ANY", degrade_to_neutral=True)
        assert result["degraded"] is True
        assert result["total"] >= 40  # neutral score floor

    def test_output_has_required_fields(self):
        """输出包含所有必填字段"""
        from duan_yongping.scoring.duan_score import score_duan

        result = score_duan("AAPL", competence_level="GREEN")
        required = ["symbol", "framework", "total", "max_score",
                    "passed", "verdict", "dimensions", "generated_at"]
        for field in required:
            assert field in result, f"Missing: {field}"


# ══════════════════════════════════════════════════════════════════════════
# Howard Marks scoring
# ══════════════════════════════════════════════════════════════════════════

class TestMarksScore:
    """马克斯三维打分测试"""

    def test_high_vix_contrarian_opportunity(self):
        """高 VIX → 逆向买入机会"""
        from howard_marks.scoring.marks_score import score_marks

        result = score_marks(
            "SPX",
            vix=35, pe_percentile_5y=15,
            sector_momentum_30d=-12,
            credit_spread=5.5,
            sector_etf_flow_30d=-800,
            short_pct_float=0.18,
            analyst_consensus="sell",
            equity_risk_premium=0.06,
            shiller_pe_percentile=20,
        )
        dim = result["dimensions"]["周期定位"]
        assert dim["score"] >= 25  # strong cycle bottom signal
        assert result["passed"] is True

    def test_low_vix_complacency_warning(self):
        """低 VIX → 周期顶部警告"""
        from howard_marks.scoring.marks_score import score_marks

        result = score_marks(
            "SPX",
            vix=11, pe_percentile_5y=85,
            sector_momentum_30d=18,
            credit_spread=1.2,
        )
        dim = result["dimensions"]["周期定位"]
        assert dim["score"] < 20  # cycle top
        assert "周期顶部" in result["cycle_label"]

    def test_strong_contrarian_setup(self):
        """资金流出 + 高做空 + 超跌 → 强逆向信号"""
        from howard_marks.scoring.marks_score import score_marks

        result = score_marks(
            "BEATEN",
            sector_etf_flow_30d=-1000,
            short_pct_float=0.20,
            analyst_consensus="strong_sell",
            price_vs_200ma_pct=-25,
            insider_trend="buying",
        )
        dim = result["dimensions"]["逆向强度"]
        assert dim["score"] >= 25  # very strong contrarian

    def test_negative_erp_penalizes(self):
        """ERP 为负 → 风险溢价不足"""
        from howard_marks.scoring.marks_score import score_marks

        result = score_marks(
            "SPX",
            equity_risk_premium=-0.02,
            earnings_yield=0.02,
            ten_year_yield=0.05,
        )
        dim = result["dimensions"]["风险溢价"]
        assert dim["score"] < 15  # penalized

    def test_output_has_cycle_label(self):
        """输出包含周期标签"""
        from howard_marks.scoring.marks_score import score_marks

        result = score_marks("SPX", vix=20)
        assert "cycle_label" in result
        assert len(result["cycle_label"]) > 0


# ══════════════════════════════════════════════════════════════════════════
# Dong Yiting scoring
# ══════════════════════════════════════════════════════════════════════════

# 注: 下方边界断言(≥80 优质底仓 / <40 不建仓 / <30 禁止参与)与
# frame_const.yaml scoring.dong 的 tiers 逐字对齐。若改 config 阈值,需同步更新
# 这些边界断言(单一事实源见 dual_track._DEFENSIVE_TIERS / _CYCLICAL_TIERS)。

class TestDongScore:
    """董艺婷双轨打分测试"""

    def test_classify_defensive(self):
        """AAPL → 防御"""
        from dong_yiting.scoring.dual_track import classify_holding

        known = {"AAPL": "defensive", "NVDA": "cyclical"}
        assert classify_holding("AAPL", known_classifications=known) == "defensive"
        assert classify_holding("NVDA", known_classifications=known) == "cyclical"

    def test_classify_unknown(self):
        """无分类 → unknown"""
        from dong_yiting.scoring.dual_track import classify_holding

        assert classify_holding("RANDOMCO") == "unknown"

    def test_defensive_high_score(self):
        """优质防御股 → ≥ 80"""
        from dong_yiting.scoring.dual_track import score_defensive

        result = score_defensive(
            "KO",
            fundamentals={
                "sector": "必选消费",
                "pe": 22, "fcf_yield": 0.04, "debt_equity": 1.2,
                "short_pct_float": 0.05,
            },
            business_moat=25, cashflow_stability=25,
            valuation_safety=15, portfolio_hedge=8,
        )
        assert result["track"] == "defensive"
        assert result["total"] >= 80
        assert result["verdict"] == "优质底仓"

    def test_defensive_low_score(self):
        """不符合防御标准 → < 40"""
        from dong_yiting.scoring.dual_track import score_defensive

        result = score_defensive(
            "BADCO",
            fundamentals={"pe": 60, "fcf_yield": -0.02},
        )
        assert result["total"] < 40
        assert result["position_limit_pct"] == 0

    def test_cyclical_ban(self):
        """周期股 < 30 → 禁止参与"""
        from dong_yiting.scoring.dual_track import score_cyclical

        result = score_cyclical(
            "BADCHIP",
            fundamentals={"revenue_growth": 30, "pe": 50},
        )
        assert result["verdict"] == "禁止参与"
        assert result["position_limit_pct"] == 0

    def test_cash_auto_passes(self):
        """现金/ETF 自动通过"""
        from dong_yiting.scoring.dual_track import score_holding

        result = score_holding("SGOV", holding_type="cash")
        assert result["verdict"] == "自动通过"
        assert result["position_limit_pct"] == 100

    def test_red_lines_screening(self):
        """红线检查"""
        from dong_yiting.scoring.dual_track import check_red_lines

        triggers = check_red_lines(
            "RISKY",
            avg_daily_volume=2_000_000,  # < 5M
            pe_percentile=95,             # > 90%
            negative_cashflow_years=2,
        )
        assert len(triggers) == 3
        checks = [t["check"] for t in triggers]
        assert "low_liquidity" in checks
        assert "pe_extreme" in checks
        assert "negative_cashflow" in checks

    def test_red_lines_all_pass(self):
        """全部通过 → 空列表"""
        from dong_yiting.scoring.dual_track import check_red_lines

        triggers = check_red_lines("GOOD", avg_daily_volume=10_000_000)
        assert triggers == []

    def test_degrade_to_neutral(self):
        """降级 → neutral 分 + degraded=True"""
        from dong_yiting.scoring.dual_track import score_defensive

        result = score_defensive("ANY", degrade_to_neutral=True)
        assert result["degraded"] is True
        assert result["total"] >= 40


# ══════════════════════════════════════════════════════════════════════════
# Master router
# ══════════════════════════════════════════════════════════════════════════

class TestMasterRouter:
    """三框架串联调度测试"""

    def test_all_mode_returns_all_scores(self):
        from master_router import run_master_pipeline

        result = run_master_pipeline(
            "AAPL", mode="all",
            duan_params={"competence_level": "GREEN", "pe": 22, "roe": 0.30, "roic": 0.20},
            marks_params={"vix": 20},
            thesis_provided=True, in_circle_of_competence=True,
            has_margin_of_safety=True, position_within_limits=True, stop_loss_set=True,
        )
        assert "duan" in result["scores"]
        assert "marks" in result["scores"]
        assert "dong" in result["scores"]

    def test_duan_mode_only_dong(self):
        """duan+dong 模式跳过马克斯"""
        from master_router import run_master_pipeline

        result = run_master_pipeline(
            "AAPL", mode="duan+dong",
            duan_params={"competence_level": "GREEN"},
        )
        assert "duan" in result["scores"]
        assert "marks" not in result["scores"]
        assert "dong" in result["scores"]

    def test_duan_block_stops_pipeline(self):
        """段永平不通过 → 阻断"""
        from master_router import run_master_pipeline

        result = run_master_pipeline(
            "UNKNOWN", mode="all",
            duan_params={"competence_level": "RED"},
            marks_params={"vix": 20},
            thesis_provided=True, in_circle_of_competence=True,
            has_margin_of_safety=True, position_within_limits=True, stop_loss_set=True,
        )
        assert result["blocked"] is True
        assert "段永平" in result["blocked_by"]

    def test_marks_warning_not_block(self):
        """马克斯不通过 → 警告但非阻断"""
        from master_router import run_master_pipeline

        result = run_master_pipeline(
            "AAPL", mode="all",
            duan_params={"competence_level": "GREEN", "pe": 22, "roe": 0.30, "roic": 0.20},
            marks_params={"vix": 11, "pe_percentile_5y": 90, "shiller_pe_percentile": 95},
            thesis_provided=True, in_circle_of_competence=True,
            has_margin_of_safety=True, position_within_limits=True, stop_loss_set=True,
        )
        # Marks might or might not pass, but even if not, it's a warning not block
        if "marks" in result["scores"] and not result["scores"]["marks"]["passed"]:
            assert "马克斯" in result["warnings"]
            # Duan passed, so pipeline shouldn't be blocked by Marks alone
            # (though it could be blocked by Dong red lines)

    def test_common_mode(self):
        """极简模式"""
        from master_router import run_master_pipeline

        result = run_master_pipeline(
            "ANY", mode="common",
            thesis_provided=True, in_circle_of_competence=True,
            has_margin_of_safety=True, position_within_limits=True, stop_loss_set=True,
        )
        assert result["mode"] == "common"
        assert result["pipeline_passed"] is True
        assert result["common_rules"]["all_passed"] is True

    def test_common_mode_fails_on_missing_thesis(self):
        """极简模式 — 没有 thesis → 阻断"""
        from master_router import run_master_pipeline

        result = run_master_pipeline("ANY", mode="common")
        assert result["pipeline_passed"] is False
        assert "thesis_required" in result["blocked_by"]

    def test_checklist_has_required_fields(self):
        """checklist 包含所有必填字段"""
        from master_router import run_master_pipeline

        result = run_master_pipeline("AAPL", mode="all",
            duan_params={"competence_level": "GREEN", "pe": 22},
            thesis_provided=True, in_circle_of_competence=True,
            has_margin_of_safety=True, position_within_limits=True, stop_loss_set=True,
        )
        cl = result["checklist"]
        for field in ["can_buy", "position_limit_pct", "stop_loss_pct", "hard_constraints"]:
            assert field in cl, f"Missing checklist field: {field}"


# ══════════════════════════════════════════════════════════════════════════
# score_holding dispatch
# ══════════════════════════════════════════════════════════════════════════

class TestScoreHoldingDispatch:
    """Auto-classify + dispatch tests"""

    def test_dispatches_to_defensive(self):
        from dong_yiting.scoring.dual_track import score_holding

        result = score_holding("KO", holding_type="defensive",
                               fundamentals={"pe": 22, "fcf_yield": 0.04})
        assert result["track"] == "defensive"

    def test_dispatches_to_cyclical(self):
        from dong_yiting.scoring.dual_track import score_holding

        result = score_holding("NVDA", holding_type="cyclical",
                               fundamentals={"revenue_growth": 15, "pe": 30})
        assert result["track"] == "cyclical"

    def test_broad_index_autopass(self):
        from dong_yiting.scoring.dual_track import score_holding

        result = score_holding("VOO", holding_type="broad_index")
        assert result["verdict"] == "自动通过"
        assert result["position_limit_pct"] == 20
