"""Unit tests for shareholder tracker classification + noise filter.

Run: pytest tests/test_shareholder.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


# ══════════════════════════════════════════════════════════════════════════
# SEC Form 4 classification
# ══════════════════════════════════════════════════════════════════════════

class TestSECClassification:
    """SEC Form 4 申报分类测试"""

    def test_open_market_buy_is_bullish(self):
        from shareholder_tracker import classify_sec_filing

        sig = classify_sec_filing(table1_code="P")
        assert sig.icon == "🟢"
        assert sig.category == "利好"
        assert sig.score_delta == +10

    def test_open_market_sell_without_plan_is_bearish(self):
        from shareholder_tracker import classify_sec_filing

        sig = classify_sec_filing(table1_code="S", is_10b51=False)
        assert sig.icon == "🔴"
        assert sig.category == "利空"
        assert sig.score_delta == -15

    def test_10b51_sell_is_neutral(self):
        from shareholder_tracker import classify_sec_filing

        sig = classify_sec_filing(table1_code="S", is_10b51=True)
        assert sig.icon == "🟡"
        assert "10b5-1" in sig.detail
        assert abs(sig.score_delta) < 10  # muted impact

    def test_f_tax_withholding_is_noise(self):
        """F = RSU tax withholding → neutral, no signal"""
        from shareholder_tracker import classify_sec_filing

        sig = classify_sec_filing(table1_code="F")
        assert sig.icon == "⚪"
        assert sig.score_delta == 0
        assert "RSU" in sig.detail or "税费" in sig.detail

    def test_cashless_exercise_not_bearish(self):
        """M (exercise) + S (sell) = cashless → not bearish"""
        from shareholder_tracker import classify_sec_filing

        sig = classify_sec_filing(table1_code="S", table2_code="M")
        assert sig.icon == "⚠️"
        assert sig.score_delta == 0
        assert "现金平仓" in sig.detail or "cashless" in sig.detail.lower()

    def test_option_exercise_and_hold_is_bullish(self):
        """M (exercise) + no S = hold → bullish"""
        from shareholder_tracker import classify_sec_filing

        sig = classify_sec_filing(table2_code="M")
        assert sig.icon == "🟢"
        assert sig.score_delta > 0

    def test_option_expire_is_neutral(self):
        from shareholder_tracker import classify_sec_filing

        for code in ("X", "W", "E"):
            sig = classify_sec_filing(table2_code=code)
            assert sig.icon == "⚪", f"{code} should be neutral"
            assert sig.score_delta == 0

    def test_gift_donation_return_are_noise(self):
        from shareholder_tracker import classify_sec_filing

        for code in ("G", "J", "D"):
            sig = classify_sec_filing(table1_code=code)
            assert sig.icon == "⚪", f"{code} should be noise"


# ══════════════════════════════════════════════════════════════════════════
# HKEX SFC DI classification
# ══════════════════════════════════════════════════════════════════════════

class TestHKEXClassification:
    """港交所披露易分类测试"""

    def test_1101_buy_is_bullish(self):
        from shareholder_tracker import classify_hkex_filing

        sig = classify_hkex_filing("1101", shares_pct=1.0, is_beneficial_owner=True)
        assert sig.icon == "🟢"
        assert sig.score_delta == +10

    def test_1201_sell_is_bearish(self):
        from shareholder_tracker import classify_hkex_filing

        sig = classify_hkex_filing("1201", shares_pct=2.0, is_beneficial_owner=True)
        assert sig.icon == "🔴"
        assert sig.score_delta == -15

    def test_1203_option_delivery_is_NOT_sell(self):
        """🚨 最关键的测试: 1203 ≠ 主动减持！

        9992.HK 泡泡马特案例 — 段永平的期權被行权交付，
        市场误以为他减持。代码必须正确识别为 ⚠️ 而非 🔴。
        """
        from shareholder_tracker import classify_hkex_filing

        sig = classify_hkex_filing("1203", shares_pct=1.5, is_beneficial_owner=True)
        assert sig.icon == "⚠️", "1203 MUST be ⚠️, NOT 🔴!"
        assert sig.score_delta == 0
        assert "非主动卖出" in sig.detail

    def test_small_change_is_noise(self):
        from shareholder_tracker import classify_hkex_filing

        sig = classify_hkex_filing("1201", shares_pct=0.3, is_beneficial_owner=True)
        assert sig.icon == "⚪"
        assert "阈值" in sig.detail

    def test_nominee_filing_ignored(self):
        from shareholder_tracker import classify_hkex_filing

        sig = classify_hkex_filing("1201", shares_pct=5.0, is_beneficial_owner=False)
        assert sig.icon == "⚪"
        assert "代名人" in sig.detail or "托管人" in sig.detail

    def test_1205_pledge_is_watch(self):
        from shareholder_tracker import classify_hkex_filing

        sig = classify_hkex_filing("1205", shares_pct=2.0, is_beneficial_owner=True)
        assert sig.icon == "🟡"
        assert sig.score_delta == -5


# ══════════════════════════════════════════════════════════════════════════
# Merging + beneficial owner consolidation
# ══════════════════════════════════════════════════════════════════════════

class TestMergeRelatedAccounts:
    def test_merge_different_accounts_same_holder(self):
        from shareholder_tracker import merge_related_accounts

        filings = [
            {"account_name": "Personal", "shares_change": 1000, "shares_pct": 1.0,
             "event_code": "1101", "market": "HK", "is_beneficial_owner": True},
            {"account_name": "Spouse", "shares_change": -500, "shares_pct": -0.5,
             "event_code": "1201", "market": "HK", "is_beneficial_owner": True},
            {"account_name": "Trust", "shares_change": 200, "shares_pct": 0.2,
             "event_code": "1101", "market": "HK", "is_beneficial_owner": True},
        ]
        merged = merge_related_accounts(filings, "Test Holder")
        assert merged.holder_name == "Test Holder"
        # Filing 1: +1000 (1101, 1.0% → bull buy)
        # Filing 2: -500 (1201, -0.5% → threshold=0.5, not <0.5, real sell)
        # Filing 3: +200 (1101, 0.2% → <0.5% threshold → noise, excluded)
        # net real_buy: 1000, real_sell: 500
        assert merged.real_buy == 1000
        assert merged.real_sell == 500
        assert len(merged.signals) == 3

    def test_nominee_filings_excluded(self):
        from shareholder_tracker import merge_related_accounts

        filings = [
            {"account_name": "Personal", "shares_change": 1000, "shares_pct": 1.0,
             "event_code": "1101", "market": "HK", "is_beneficial_owner": True},
            {"account_name": "Custodian", "shares_change": -5000, "shares_pct": -5.0,
             "event_code": "1201", "market": "HK", "is_beneficial_owner": False},
        ]
        merged = merge_related_accounts(filings, "Test Holder")
        # Custodian excluded
        assert merged.real_buy == 1000
        assert merged.real_sell == 0  # custodian ignored

    def test_merge_is_noise_when_small(self):
        from shareholder_tracker import merge_related_accounts

        filings = [
            {"account_name": "Personal", "shares_change": 10, "shares_pct": 0.01,
             "event_code": "1201", "market": "HK", "is_beneficial_owner": True},
        ]
        merged = merge_related_accounts(filings, "Test Holder")
        assert merged.is_noise is True


# ══════════════════════════════════════════════════════════════════════════
# Three-layer noise filter
# ══════════════════════════════════════════════════════════════════════════

class TestNoiseFilter:
    def test_pure_noise_discarded(self):
        from shareholder_tracker import SignalResult, apply_noise_filter

        signals = [
            SignalResult("⚪", "中性", "F税费代扣", 0),
            SignalResult("⚪", "中性", "X期權到期", 0),
            SignalResult("⚪", "中性", "代名人申报", 0),
        ]
        filtered = apply_noise_filter(signals)
        assert len(filtered) == 0

    def test_real_signals_kept(self):
        from shareholder_tracker import SignalResult, apply_noise_filter

        signals = [
            SignalResult("🟢", "利好", "真实买入", +10),
            SignalResult("🔴", "利空", "真实卖出", -15),
        ]
        filtered = apply_noise_filter(signals)
        assert len(filtered) == 2

    def test_derivative_only_is_noise(self):
        """仅有衍生品结算 → 全部归零为噪音"""
        from shareholder_tracker import SignalResult, apply_noise_filter

        signals = [
            SignalResult("⚠️", "中性", "行权+平仓", 0),
            SignalResult("⚠️", "中性", "期權交付", 0),
        ]
        filtered = apply_noise_filter(signals)
        assert len(filtered) == 1
        assert filtered[0].icon == "⚪"
        assert "衍生品结算" in filtered[0].detail

    def test_sector_momentum_amplifies_buy(self):
        """板块超跌 + 增持 → 信号强化"""
        from shareholder_tracker import SignalResult, apply_noise_filter

        signals = [
            SignalResult("🟢", "利好", "真实买入", +10),
        ]
        filtered = apply_noise_filter(signals, industry_momentum_30d=-15)
        assert filtered[0].score_delta > 10  # amplified
        assert "逆势" in filtered[0].detail

    def test_sector_momentum_dampens_sell(self):
        """板块过热 + 减持 → 信号弱化"""
        from shareholder_tracker import SignalResult, apply_noise_filter

        signals = [
            SignalResult("🔴", "利空", "真实卖出", -15),
        ]
        filtered = apply_noise_filter(signals, industry_momentum_30d=20)
        assert abs(filtered[0].score_delta) < 15  # dampened
        assert "过热" in filtered[0].detail


# ══════════════════════════════════════════════════════════════════════════
# Master scoring integration
# ══════════════════════════════════════════════════════════════════════════

class TestShareholderScoringIntegration:
    def test_buy_signal_boosts_duan_score(self):
        from shareholder_tracker import SignalResult, apply_shareholder_signal

        base = {
            "symbol": "AAPL",
            "framework": "duan",
            "total": 65,
            "dimensions": {
                "能力圈": {"score": 25, "max": 25, "detail": ""},
                "安全边际": {"score": 15, "max": 30, "detail": ""},
                "护城河": {"score": 15, "max": 25, "detail": ""},
                "好生意": {"score": 10, "max": 20, "detail": ""},
            },
        }
        signals = [SignalResult("🟢", "利好", "大股东增持", +10)]
        result = apply_shareholder_signal(base, signals, framework="duan")
        assert result["shareholder_adjustment"] == 10
        assert result["total"] == 75  # 65 + 10

    def test_sell_signal_reduces_marks_score(self):
        from shareholder_tracker import SignalResult, apply_shareholder_signal

        base = {
            "symbol": "SPX",
            "framework": "marks",
            "total": 55,
            "dimensions": {
                "周期定位": {"score": 25, "max": 40, "detail": ""},
                "逆向强度": {"score": 20, "max": 35, "detail": ""},
                "风险溢价": {"score": 10, "max": 25, "detail": ""},
            },
        }
        signals = [SignalResult("🔴", "利空", "大股东减持", -15)]
        result = apply_shareholder_signal(base, signals, framework="marks")
        assert result["shareholder_adjustment"] == -15
        assert result["total"] == 40  # 55 - 15

    def test_no_signals_no_change(self):
        from shareholder_tracker import SignalResult, apply_shareholder_signal

        base = {
            "symbol": "AAPL",
            "framework": "duan",
            "total": 70,
            "dimensions": {},
        }
        result = apply_shareholder_signal(base, [], framework="duan")
        assert result["shareholder_adjustment"] == 0
        assert result["total"] == 70


# ══════════════════════════════════════════════════════════════════════════
# Edge cases: 泡泡马特 9992.HK real-world scenario
# ══════════════════════════════════════════════════════════════════════════

class TestPopMartRealScenario:
    """9992.HK 泡泡马特 — 段永平 1203 期權行权交付案例

    2026-08 市场将段永平的期權行权交付 (1203) 误读为减持，
    导致大跌。代码必须正确识别此场景。
    """

    def test_1203_not_classified_as_sell(self):
        """1203 绝对不能归类为 🔴 利空"""
        from shareholder_tracker import classify_hkex_filing

        sig = classify_hkex_filing("1203", shares_pct=1.5, is_beneficial_owner=True)

        # The whole point: 1203 ≠ real sell
        assert sig.icon != "🔴", (
            "BUG: 1203 should NOT be classified as bearish sell! "
            "This is derivative settlement, not active selling.")
        assert sig.icon == "⚠️"
        assert sig.score_delta == 0

    def test_1203_does_not_trigger_sell_alert(self):
        """1203 不触发减持告警"""
        from shareholder_tracker import SignalResult, apply_noise_filter

        signals = [
            SignalResult("⚠️", "中性", "期權行权交付(非主动卖出)", 0),
        ]
        filtered = apply_noise_filter(signals)
        # Should not produce any sell alert
        has_bearish = any(s.icon == "🔴" for s in filtered)
        assert not has_bearish, (
            "BUG: 1203 should not generate sell alert! Market misread this.")

    def test_full_popmart_scenario(self):
        """完整泡泡马特场景模拟"""
        from shareholder_tracker import (
            classify_hkex_filing, merge_related_accounts,
            apply_noise_filter, apply_shareholder_signal,
        )

        # 段永平在 9992.HK 的申报记录
        filings_raw = [
            {"account_name": "Duan Personal", "symbol": "9992.HK",
             "shares_change": -1_200_000, "shares_pct": -1.5,
             "event_code": "1203", "market": "HK", "is_beneficial_owner": True},
        ]

        # Step 1: Merge accounts
        merged = merge_related_accounts(filings_raw, "段永平")

        # Step 2: Classify (should be derivative, not sell)
        assert merged.real_sell == 0, "No real selling occurred"
        assert merged.signals[0].icon == "⚠️"

        # Step 3: Noise filter
        filtered = apply_noise_filter(merged.signals)
        # Only derivative activity → should be neutralized
        real_signals = [s for s in filtered if s.icon in ("🔴", "🟢")]
        assert len(real_signals) == 0, "No real buy/sell signals"

        # Step 4: Should NOT modify Duan scoring
        duan_base = {
            "symbol": "9992.HK", "framework": "duan", "total": 75,
            "dimensions": {
                "安全边际": {"score": 20, "max": 30, "detail": ""},
            },
        }
        result = apply_shareholder_signal(duan_base, filtered, framework="duan")
        assert result["shareholder_adjustment"] == 0
        assert result["total"] == 75  # unchanged — no real signal
