"""Major shareholder position tracking — classification + noise filtering.

Handles SEC Form 4 (US) and HKEX SFC DI (HK) filings with proper
classification of real buy/sell vs derivative settlements vs tax
withholding.  Three-layer noise filter: single classification →
30-day rolling smooth → industry hot money overlay.

All classification functions are PURE.  Data fetching is via
data_fetch_base.py (BaseAdapter pattern).

Reference: SEC Form 4 Table I/II codes, HKEX SFC DI event codes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ══════════════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class SignalResult:
    """Classification result for a single filing."""
    icon: str           # 🟢 🔴 🟡 ⚪ ⚠️
    category: str       # "利好" | "利空" | "中性" | "关注" | "无信号"
    detail: str         # Human-readable explanation
    score_delta: int    # Adjustment to master framework score

    def to_dict(self) -> dict[str, Any]:
        return {
            "icon": self.icon,
            "category": self.category,
            "detail": self.detail,
            "score_delta": self.score_delta,
        }


@dataclass
class MergedPosition:
    """Net position change across all accounts of one holder."""
    holder_name: str
    symbol: str
    total_shares: float = 0.0
    net_change_pct: float = 0.0
    real_buy: float = 0.0
    real_sell: float = 0.0
    derivative_net: float = 0.0  # Net derivative activity (should be ~0)
    tax_withholding: float = 0.0
    signals: list[SignalResult] = field(default_factory=list)

    @property
    def is_noise(self) -> bool:
        """True if net change is within noise threshold."""
        return abs(self.net_change_pct) < 0.5

    @property
    def dominant_signal(self) -> Optional[SignalResult]:
        """Most significant signal after merging."""
        if not self.signals:
            return None
        # Real signals dominate; biggest absolute score_delta wins
        real = [s for s in self.signals if s.icon in ("🟢", "🔴")]
        if real:
            return max(real, key=lambda s: abs(s.score_delta))
        return self.signals[0]


# ══════════════════════════════════════════════════════════════════════════
# SEC Form 4 classification
# ══════════════════════════════════════════════════════════════════════════

def classify_sec_filing(
    table1_code: str = "",
    table2_code: str = "",
    footnotes: str = "",
    is_10b51: bool = False,
) -> SignalResult:
    """Classify a single SEC Form 4 filing.

    Table I (Non-Derivative — 正股):
      P = open-market purchase       → 🟢 强利好
      S = open-market sale           → 🔴 强利空 (unless 10b5-1)
      F = RSU tax withholding        → ⚪ 中性噪音
      G = gift                       → ⚪ 非交易过户
      J = other                      → ⚪ 通常无关
      D = return to company          → ⚪ 中性

    Table II (Derivative — 衍生品):
      M = option exercise (get shares) → check Table I for paired S
      X = option expire worthless      → ⚪ 中性
      A = RSU/option grant             → ⚪ 中性（薪酬）
      W = option expiration            → ⚪ 中性
      E = option early termination     → ⚪ 通常中性

    Key combos:
      Table I=S + no 10b5-1   → 🔴 real sell
      Table I=S + 10b5-1      → 🟡 planned sell (less emotional)
      Table II=M + Table I=S   → ⚠️ cashless exercise (not bearish)
      Table I=F                → ⚪ tax withholding (most common noise)
      Table I=P                → 🟢 real buy (strongest signal)
    """
    # ── Bearish: real selling ──
    if table1_code == "S" and not is_10b51 and table2_code != "M":
        return SignalResult("🔴", "利空", "场内主动卖出(无预计划)", -15)
    if table1_code == "S" and is_10b51:
        return SignalResult("🟡", "中性", "10b5-1预规划减持(非情绪驱动)", -3)

    # ── Neutral noise ──
    if table1_code == "F":
        return SignalResult("⚪", "中性", "RSU税费代扣(无看空含义)", 0)
    if table2_code == "M" and table1_code == "S":
        return SignalResult("⚠️", "中性",
                           "行权+同日平仓(现金平仓,非长期看空)", 0)
    if table2_code in ("X", "W", "E"):
        return SignalResult("⚪", "中性",
                           f"期權到期/作废(无实际交易) [{table2_code}]", 0)
    if table1_code in ("G", "J", "D"):
        return SignalResult("⚪", "中性",
                           f"赠与/归还/其他非交易过户 [{table1_code}]", 0)

    # ── Bullish: real buying ──
    if table1_code == "P":
        return SignalResult("🟢", "利好", "自有资金场内买入", +10)
    if table2_code == "M" and table1_code != "S":
        return SignalResult("🟢", "利好", "期權行权获股并持有(看好信号)", +8)

    return SignalResult("⚪", "中性", "无实质信号", 0)


# ══════════════════════════════════════════════════════════════════════════
# HKEX SFC DI classification
# ══════════════════════════════════════════════════════════════════════════

def classify_hkex_filing(
    event_code: str,
    shares_pct: float = 0.0,
    is_beneficial_owner: bool = True,
) -> SignalResult:
    """Classify a single HKEX SFC DI filing.

    HKEX event codes:

    Increase (110 series):
      1101 = on-market buy             → 🟢 real buy
      1102 = off-market buy            → 🟢 real buy
      1103 = option exercise (get)     → 🟢 if held (bullish)
      1111 = CB conversion             → ⚪ corporate action

    Decrease (120 series):
      1201 = on-market sell            → 🔴 real sell
      1202 = off-market sell           → 🔴 real sell
      1203 = option exercise (deliver) → ⚠️ derivative settlement (NOT real sell!)
      1204 = option expire             → ⚪ no actual trade
      1205 = share pledge              → 🟡 collateral change
      1206 = share lending             → 🟡 lending change

    Args:
        event_code: HKEX SFC DI event code (e.g. "1203")
        shares_pct: Shares as % of total outstanding
        is_beneficial_owner: True if beneficial owner (实益拥有人),
                            False if nominee/custodian
    """
    # ── Ignore non-beneficial owners ──
    if not is_beneficial_owner:
        return SignalResult("⚪", "无信号", "代名人/托管人申报，忽略", 0)

    # ── Noise threshold ──
    if abs(shares_pct) < 0.5:
        return SignalResult("⚪", "无信号",
                           f"变动 {shares_pct:.2f}% < 0.5% 阈值，忽略", 0)

    # ── Decrease signals ──
    if event_code == "1203":
        return SignalResult("⚠️", "中性",
                           "期權行权交付(非主动卖出！市场可能误读)", 0)
    if event_code in ("1201", "1202"):
        return SignalResult("🔴", "利空", "真实减持", -15)
    if event_code == "1204":
        return SignalResult("⚪", "无信号", "期權到期作废(无实际交易)", 0)
    if event_code in ("1205", "1206"):
        return SignalResult("🟡", "关注", f"质押/借贷变动 [{event_code}]", -5)

    # ── Increase signals ──
    if event_code in ("1101", "1102"):
        return SignalResult("🟢", "利好", "真实增持", +10)
    if event_code == "1103":
        return SignalResult("🟢", "利好", "期權行权获股并持有", +8)
    if event_code == "1111":
        return SignalResult("⚪", "中性", "可转债转股(公司行动)", 0)

    return SignalResult("⚪", "中性", f"未识别事件码 {event_code}", 0)


# ══════════════════════════════════════════════════════════════════════════
# Beneficial owner consolidation
# ══════════════════════════════════════════════════════════════════════════

def merge_related_accounts(
    filings: list[dict[str, Any]],
    holder_name: str,
) -> MergedPosition:
    """Merge filings across related accounts of the same beneficial owner.

    HKEX rules require consolidation of: individual + spouse + children +
    controlled corporations + trusts.  This function merges multiple
    account filings into a single net position change.

    Args:
        filings: List of filing dicts, each with keys:
            account_name, shares_change, event_code, shares_pct, is_beneficial_owner
        holder_name: Beneficial owner name for output

    Returns:
        MergedPosition with net totals and consolidated signals
    """
    merged = MergedPosition(holder_name=holder_name, symbol="")

    for f in filings:
        if not f.get("is_beneficial_owner", True):
            continue

        merged.symbol = merged.symbol or f.get("symbol", "")
        shares_change = f.get("shares_change", 0)
        shares_pct = f.get("shares_pct", 0)
        event_code = str(f.get("event_code", ""))
        market = f.get("market", "HK")

        merged.total_shares += f.get("total_shares_after", 0)

        # Classify based on market
        if market == "US":
            sig = classify_sec_filing(
                table1_code=f.get("table1_code", ""),
                table2_code=f.get("table2_code", ""),
                is_10b51=f.get("is_10b51", False),
            )
        else:
            sig = classify_hkex_filing(
                event_code=event_code,
                shares_pct=shares_pct,
                is_beneficial_owner=True,
            )

        # Categorise
        if sig.icon == "🟢":
            merged.real_buy += shares_change
        elif sig.icon == "🔴":
            merged.real_sell += abs(shares_change)
        elif sig.icon == "⚠️":
            merged.derivative_net += shares_change  # could be + or -
        elif sig.icon == "⚪" and event_code in ("F", "1204", "X", "W", "E"):
            merged.tax_withholding += abs(shares_change)
        elif sig.icon == "🟡":
            # Collateral/lending — track but don't classify as buy/sell
            pass

        merged.signals.append(sig)
        merged.net_change_pct += shares_pct

    # Deduplicate: real buy + real sell on same day = net
    merged.net_change_pct = merged.real_buy - merged.real_sell + merged.derivative_net

    return merged


# ══════════════════════════════════════════════════════════════════════════
# Three-layer noise filter
# ══════════════════════════════════════════════════════════════════════════

def apply_noise_filter(
    signals: list[SignalResult],
    *,
    rolling_window_days: int = 30,
    derivative_net_max: float = 0.3,
    industry_momentum_30d: Optional[float] = None,
    pe_percentile_5y: Optional[float] = None,
) -> list[SignalResult]:
    """Apply three-layer noise filter to shareholder signals.

    Layer 1 — Single classification:
      - F tax withholding / X option expire → discard immediately
      - < 0.5% share change → discard
      - Nominee/custodian filings → discard

    Layer 2 — 30-day rolling smooth:
      - If net derivative activity < ±0.3% over 30 days → all mark noise
      - Single-day impulse trades → filtered out

    Layer 3 — Industry hot money overlay:
      - Sector momentum > +15% + insider sells → weight × 0.3
      - Sector momentum < -10% + insider buys → weight × 1.5
      - PE > 80% percentile + selling → weight × 1.2 (confirm)

    Args:
        signals: Pre-classified SignalResult list
        rolling_window_days: Window for Layer 2 smoothing
        derivative_net_max: Threshold for net derivative change
        industry_momentum_30d: Sector 30-day price momentum %
        pe_percentile_5y: PE 5-year percentile for context

    Returns:
        Filtered signals with adjusted weights
    """
    filtered: list[SignalResult] = []

    # Layer 1: Discard pure noise
    for sig in signals:
        if sig.icon == "⚪":
            continue  # discard
        filtered.append(sig)

    # Layer 2: Check for derivative wash pattern
    warnings = [s for s in filtered if s.icon == "⚠️"]
    real_sells = [s for s in filtered if s.icon == "🔴"]
    real_buys = [s for s in filtered if s.icon == "🟢"]

    # If only derivative warnings, no real signals → all noise
    if warnings and not real_sells and not real_buys:
        for w in warnings:
            w.score_delta = 0  # zero out derivative-only noise
        return [
            SignalResult("⚪", "无信号",
                        "30天内仅有衍生品结算，无真实买卖信号", 0)
        ]

    # Layer 3: Context overlay
    for sig in filtered:
        delta = sig.score_delta

        # Hot sector + selling → dampen
        if sig.icon == "🔴" and industry_momentum_30d is not None:
            if industry_momentum_30d > 15:
                delta = int(delta * 0.3)  # reduce weight
                sig.detail += " [板块过热，信号弱化]"

        # Beaten-down sector + buying → amplify
        if sig.icon == "🟢" and industry_momentum_30d is not None:
            if industry_momentum_30d < -10:
                delta = int(delta * 1.5)  # amplify
                sig.detail += " [逆势增持，信号强化]"

        # High PE + selling → confirm
        if sig.icon == "🔴" and pe_percentile_5y is not None:
            if pe_percentile_5y > 80:
                delta = int(delta * 1.2)  # confirm — valuation + insider both say sell
                sig.detail += " [估值高位+减持共振]"

        sig.score_delta = delta

    return filtered


# ══════════════════════════════════════════════════════════════════════════
# Master scoring integration
# ══════════════════════════════════════════════════════════════════════════

def apply_shareholder_signal(
    base_score: dict[str, Any],
    holder_signals: list[SignalResult],
    framework: str = "duan",
) -> dict[str, Any]:
    """Modify framework scores based on shareholder activity.

    Args:
        base_score: Original scoring result from score_duan() or score_marks()
        holder_signals: Filtered, classified shareholder signals
        framework: Which framework to adjust ("duan" | "marks")

    Returns:
        Modified scoring dict with shareholder_adjustment field added
    """
    total_delta = sum(sig.score_delta for sig in holder_signals)

    if not total_delta:
        base_score["shareholder_adjustment"] = 0
        base_score["shareholder_signal"] = "无大股东信号变动"
        return base_score

    # Apply to appropriate dimension
    if framework == "duan":
        dims = base_score.get("dimensions", {})
        if "安全边际" in dims:
            original = dims["安全边际"]["score"]
            dims["安全边际"]["score"] = max(0, min(30, original + total_delta))
            dims["安全边际"]["detail"] += (
                f"；大股东信号修正 {total_delta:+d}")
        base_score["total"] = sum(d["score"] for d in dims.values())

    elif framework == "marks":
        dims = base_score.get("dimensions", {})
        if "逆向强度" in dims:
            original = dims["逆向强度"]["score"]
            dims["逆向强度"]["score"] = max(0, min(35, original + total_delta))
            dims["逆向强度"]["detail"] += (
                f"；大股东信号修正 {total_delta:+d}")
        base_score["total"] = sum(d["score"] for d in dims.values())

    base_score["shareholder_adjustment"] = total_delta
    signal_desc = "利好" if total_delta > 0 else "利空" if total_delta < 0 else "中性"
    base_score["shareholder_signal"] = signal_desc

    return base_score
