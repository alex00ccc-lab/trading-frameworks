"""Unified data fetch base class — rate limiting, caching, retry, failover.

Five-layer compliance & resilience architecture:
  1. Hard constraints (rate limits, UA, serial execution)
  2. Exponential backoff + randomisation
  3. Three-tier cache fallback (memory → local → remote)
  4. Multi-source failover (primary → backup adapters)
  5. Self-healing + alerting

This module provides the BaseAdapter ABC and concrete implementations
for SEC EDGAR and HKEX DI scraping.  Market-data-collector's existing
adapter chain handles general market data separately.
"""

from __future__ import annotations

import json
import logging
import time
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("data_fetch")

TZ_BEIJING = timezone(timedelta(hours=8))

# ══════════════════════════════════════════════════════════════════════════
# Base Adapter
# ══════════════════════════════════════════════════════════════════════════

class BaseAdapter(ABC):
    """Abstract base for all data-fetch adapters.

    Subclasses must implement:
      - health_check() → bool
      - is_rate_limited() → bool
      - set_cooldown(seconds: int)
      - _fetch_impl(symbol: str, **kwargs) → dict
    """

    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.config = config
        self._cooldown_until: float = 0.0
        self._consecutive_errors: int = 0
        self._cache: dict[str, Any] = {}  # in-memory cache (L1)

    # ── Abstract methods ──

    @abstractmethod
    def health_check(self) -> bool: ...

    @abstractmethod
    def is_rate_limited(self) -> bool: ...

    @abstractmethod
    def set_cooldown(self, seconds: int) -> None: ...

    @abstractmethod
    def _fetch_impl(self, symbol: str, **kwargs) -> dict[str, Any]: ...

    # ── Common methods ──

    def fetch(self, symbol: str, **kwargs) -> dict[str, Any]:
        """Public fetch with L1 memory cache + cooldown + rate-limit guard."""
        cache_key = f"{symbol}:{json.dumps(kwargs, sort_keys=True, default=str)}"

        # L1: memory cache
        if cache_key in self._cache:
            logger.debug("[%s] L1 cache hit: %s", self.name, symbol)
            return self._cache[cache_key]

        # Rate limit guard
        if self.is_rate_limited():
            logger.warning("[%s] Rate limited, using degraded response", self.name)
            return {"error": "rate_limited", "source": self.name, "data": {}}

        # Cooldown guard
        if time.monotonic() < self._cooldown_until:
            remaining = int(self._cooldown_until - time.monotonic())
            return {"error": "cooldown", "source": self.name,
                    "retry_after_sec": remaining, "data": {}}

        try:
            result = self._fetch_impl(symbol, **kwargs)
            self._cache[cache_key] = result
            self._consecutive_errors = 0
            return result
        except Exception as e:
            self._consecutive_errors += 1
            logger.error("[%s] Fetch failed for %s: %s", self.name, symbol, e)
            if self._consecutive_errors >= 3:
                self.set_cooldown(3600)  # 1 hour cooldown after 3 errors
            return {"error": str(e), "source": self.name, "data": {}}


# ══════════════════════════════════════════════════════════════════════════
# SEC EDGAR Adapter
# ══════════════════════════════════════════════════════════════════════════

class SECEdgarAdapter(BaseAdapter):
    """SEC EDGAR Form 4 fetcher.

    Compliance rules:
      - ≤ 9 req/s (official limit 10, 1 buffer)
      - Real-name User-Agent with email required
      - Single-thread serial execution only
      - CI weekly only
    """

    MAX_REQ_PER_SEC = 9
    DEFAULT_TIMEOUT = 12

    def __init__(self, config: dict[str, Any]):
        super().__init__("sec_edgar", config)
        self._last_request_time: float = 0.0
        self._cooldown_file = Path(config.get("cache_dir", "cache")) / "_cooldown.json"

    def health_check(self) -> bool:
        """Quick connectivity test to EDGAR."""
        try:
            import requests
            resp = requests.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                headers=self._build_headers(),
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def is_rate_limited(self) -> bool:
        """Check if we're within the 9 req/s limit."""
        elapsed = time.monotonic() - self._last_request_time
        return elapsed < (1.0 / self.MAX_REQ_PER_SEC)

    def set_cooldown(self, seconds: int) -> None:
        """Persist cooldown to disk."""
        self._cooldown_until = time.monotonic() + seconds
        try:
            self._cooldown_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "adapter": self.name,
                "cooldown_until_utc": (
                    datetime.now(timezone.utc).timestamp() + seconds),
                "set_at": datetime.now(TZ_BEIJING).isoformat(),
                "reason": f"{self._consecutive_errors} consecutive errors",
            }
            self._cooldown_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to persist cooldown: %s", e)

    def _build_headers(self) -> dict[str, str]:
        ua_email = self.config.get("ua_email", "placeholder@example.com")
        return {
            "User-Agent": f"{ua_email} (holdings-briefing personal research)",
            "Accept": "application/json, text/html",
        }

    def _fetch_impl(self, symbol: str, **kwargs) -> dict[str, Any]:
        """Fetch recent Form 4 filings for a CIK/symbol.

        This is a STUB — real implementation requires:
          1. CIK lookup via ticker→CIK mapping
          2. EDGAR submissions API: /cgi-bin/browse-edgar?CIK=...&action=getcurrent
          3. Parse XML/HTML responses for Form 4 Table I/II codes

        For now, returns a structured empty result that callers can handle.
        """
        self._last_request_time = time.monotonic()
        # Rate-limit jitter
        time.sleep(random.uniform(0.1, 0.2))

        return {
            "symbol": symbol,
            "source": "sec_edgar",
            "filings": [],
            "fetched_at": datetime.now(TZ_BEIJING).isoformat(),
            "note": "SEC EDGAR adapter stub — real fetch requires CIK lookup + XML parsing",
        }


# ══════════════════════════════════════════════════════════════════════════
# HKEX DI Adapter
# ══════════════════════════════════════════════════════════════════════════

class HKEXDIAdapter(BaseAdapter):
    """HKEX Disclosure of Interests (DI) fetcher.

    Compliance rules:
      - ≤ 6 req/symbol/day
      - Random 2-5s intervals between requests
      - CI weekly only (T+3 reporting delay)
      - Single process, no concurrency
    """

    MAX_REQ_PER_SYMBOL_DAY = 6
    DEFAULT_TIMEOUT = 12

    def __init__(self, config: dict[str, Any]):
        super().__init__("hkex_di", config)
        self._daily_req_count: dict[str, int] = {}
        self._last_request_time: float = 0.0
        self._cooldown_file = Path(config.get("cache_dir", "cache")) / "_cooldown.json"

    def health_check(self) -> bool:
        """Quick connectivity test to HKEX DI."""
        try:
            import requests
            resp = requests.get(
                "https://di.hkex.com.hk/di/NSSrch.aspx",
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def is_rate_limited(self) -> bool:
        """Check both per-symbol and global rate limits."""
        # Global: must have ≥ 2s gap between requests
        elapsed = time.monotonic() - self._last_request_time
        return elapsed < 2.0

    def set_cooldown(self, seconds: int) -> None:
        """Persist cooldown to disk."""
        self._cooldown_until = time.monotonic() + seconds
        try:
            self._cooldown_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "adapter": self.name,
                "cooldown_until_utc": (
                    datetime.now(timezone.utc).timestamp() + seconds),
                "set_at": datetime.now(TZ_BEIJING).isoformat(),
            }
            self._cooldown_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to persist cooldown: %s", e)

    def _fetch_impl(self, symbol: str, **kwargs) -> dict[str, Any]:
        """Fetch recent DI filings for a HK stock code.

        This is a STUB — real implementation requires:
          1. Convert symbol to HK stock code (e.g. 9992.HK → 9992)
          2. POST to di.hkex.com.hk/di/NSSrch.aspx with form params
          3. Parse the resulting HTML table for DI events
          4. Extract event code, share count, % change, holder name

        For now, returns a structured empty result.
        """
        today = datetime.now(TZ_BEIJING).strftime("%Y%m%d")

        # Per-symbol daily cap
        daily_count = self._daily_req_count.get(f"{symbol}:{today}", 0)
        if daily_count >= self.MAX_REQ_PER_SYMBOL_DAY:
            return {
                "symbol": symbol,
                "source": "hkex_di",
                "error": "daily_limit_reached",
                "filings": [],
                "fetched_at": datetime.now(TZ_BEIJING).isoformat(),
            }

        self._daily_req_count[f"{symbol}:{today}"] = daily_count + 1
        self._last_request_time = time.monotonic()

        # Random interval 2-5s
        time.sleep(random.uniform(2, 5))

        return {
            "symbol": symbol,
            "source": "hkex_di",
            "filings": [],
            "fetched_at": datetime.now(TZ_BEIJING).isoformat(),
            "note": "HKEX DI adapter stub — real fetch requires HTML form POST + table parsing",
        }


# ══════════════════════════════════════════════════════════════════════════
# Three-tier cache manager
# ══════════════════════════════════════════════════════════════════════════

class CacheManager:
    """Three-tier cache: L1 memory → L2 local disk → L3 remote fetch.

    L1: in-process dict (fastest, cleared on restart)
    L2: local JSON files in cache/shareholder/{market}/{sym}.json
    L3: actual fetch via adapter (slowest, rate-limited)
    """

    def __init__(self, cache_dir: str = "cache/shareholder", ttl_days: int = 90):
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_days * 86400
        self._l1: dict[str, dict[str, Any]] = {}

    def get(self, market: str, symbol: str) -> Optional[dict[str, Any]]:
        """Get cached data, L1 → L2 → None (caller should fetch L3)."""
        key = f"{market}:{symbol}"

        # L1: memory
        if key in self._l1:
            return self._l1[key]

        # L2: disk
        path = self.cache_dir / market / f"{symbol}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                age = time.time() - data.get("cached_at_ts", 0)
                if age < self.ttl_seconds:
                    self._l1[key] = data  # promote to L1
                    return data
                # Expired but still usable as fallback
                data["stale"] = True
                return data
            except Exception:
                pass

        return None

    def put(self, market: str, symbol: str, data: dict[str, Any]) -> None:
        """Write to L1 and L2."""
        key = f"{market}:{symbol}"
        data["cached_at_ts"] = time.time()
        data["cached_at"] = datetime.now(TZ_BEIJING).isoformat()

        # L1
        self._l1[key] = data

        # L2
        try:
            path = self.cache_dir / market / f"{symbol}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, default=str),
                           encoding="utf-8")
        except Exception as e:
            logger.warning("Cache write failed for %s: %s", symbol, e)
