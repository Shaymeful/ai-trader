"""Daily / session loss kill switches for the runner execution path.

These guards block new *risk-increasing* orders once account-equity drawdown,
measured against equity baselines, breaches ``MAX_DAILY_LOSS`` or
``MAX_SESSION_LOSS``. Risk-reducing (exit / flatten) orders are never blocked.

Baselines:
  - ``session_start_equity``: captured once per process (resets on restart,
    mirroring the existing session-PnL semantics). Held in memory on the guard.
  - ``day_start_equity``: persisted per US/Eastern trading date in a JSON state
    file so the daily limit cannot be reset by restarting the bot mid-day.

Drawdown is computed from broker account equity, which already reflects realized
PnL, unrealized PnL, and fees — so this is a true account-level circuit breaker
rather than a strategy-level PnL estimate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from src.app.state import get_today_date_eastern

logger = logging.getLogger("ai-trader")

_DEFAULT_STATE_PATH = Path("state/loss_limits.json")


@dataclass
class LossLimitState:
    """Result of evaluating the loss kill switches against current equity."""

    tripped: bool
    reasons: list[str] = field(default_factory=list)
    current_equity: Decimal | None = None
    day_start_equity: Decimal | None = None
    session_start_equity: Decimal | None = None
    daily_drawdown: Decimal | None = None
    session_drawdown: Decimal | None = None
    equity_available: bool = True


class LossLimitGuard:
    """Tracks equity baselines and evaluates the daily/session loss kill switches.

    A single instance is meant to live for the lifetime of a runner process so the
    in-memory ``session_start_equity`` baseline is stable across loop iterations.
    """

    def __init__(self, state_path: Path | None = None):
        self._state_path = state_path or _DEFAULT_STATE_PATH
        self._session_start_equity: Decimal | None = None

    # ---- baselines ----------------------------------------------------------
    def capture_session_start(self, equity: Decimal) -> Decimal:
        """Return the session-start equity baseline, capturing it on first call."""
        if self._session_start_equity is None:
            self._session_start_equity = equity
            logger.info(f"Session-start equity baseline captured: ${equity:.2f}")
        return self._session_start_equity

    def day_start_equity(self, equity: Decimal, *, today: str | None = None) -> Decimal:
        """Return the persisted day-start equity for ``today`` (Eastern date).

        On the first observation of a new trading date the current equity becomes
        the baseline and is persisted, so a mid-day restart cannot reset it.
        """
        today = today or get_today_date_eastern()
        data = self._load()
        existing = data.get(today)
        if existing is not None:
            return Decimal(str(existing))
        data[today] = str(equity)
        self._save(data)
        logger.info(f"Day-start equity baseline for {today} set: ${equity:.2f}")
        return equity

    # ---- evaluation ---------------------------------------------------------
    def evaluate(
        self,
        *,
        current_equity: Decimal | None,
        max_daily_loss: Decimal | None,
        max_session_loss: Decimal | None,
        today: str | None = None,
    ) -> LossLimitState:
        """Evaluate the kill switches. Fails closed (tripped) if equity is unknown."""
        # Fail closed when equity is unavailable: block new risk. Do NOT set any
        # baseline from a bad reading.
        if current_equity is None:
            return LossLimitState(
                tripped=True,
                reasons=[
                    "Account equity unavailable — failing closed on new "
                    "risk-increasing orders"
                ],
                equity_available=False,
            )

        session_start = self.capture_session_start(current_equity)
        day_start = self.day_start_equity(current_equity, today=today)

        session_dd = session_start - current_equity
        daily_dd = day_start - current_equity

        reasons: list[str] = []
        tripped = False

        if max_daily_loss is not None and daily_dd >= max_daily_loss:
            tripped = True
            reasons.append(
                f"Daily loss ${daily_dd:.2f} >= limit ${max_daily_loss:.2f} "
                f"(day-start equity ${day_start:.2f} -> ${current_equity:.2f})"
            )
        if max_session_loss is not None and session_dd >= max_session_loss:
            tripped = True
            reasons.append(
                f"Session loss ${session_dd:.2f} >= limit ${max_session_loss:.2f} "
                f"(session-start equity ${session_start:.2f} -> ${current_equity:.2f})"
            )

        return LossLimitState(
            tripped=tripped,
            reasons=reasons,
            current_equity=current_equity,
            day_start_equity=day_start,
            session_start_equity=session_start,
            daily_drawdown=daily_dd,
            session_drawdown=session_dd,
        )

    # ---- persistence --------------------------------------------------------
    def _load(self) -> dict:
        try:
            if self._state_path.exists():
                with open(self._state_path) as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read loss-limit state {self._state_path}: {e}")
        return {}

    def _save(self, data: dict) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write loss-limit state {self._state_path}: {e}")


_DEFAULT_GUARD: LossLimitGuard | None = None


def get_default_guard() -> LossLimitGuard:
    """Return the process-lifetime singleton guard.

    Using a singleton keeps ``session_start_equity`` stable across the many
    ``run_paper_mode`` calls a long-running loop makes within one process.
    """
    global _DEFAULT_GUARD
    if _DEFAULT_GUARD is None:
        _DEFAULT_GUARD = LossLimitGuard()
    return _DEFAULT_GUARD


def fetch_account_equity(broker) -> Decimal | None:
    """Best-effort fetch of account equity from a broker; ``None`` if unavailable."""
    try:
        if hasattr(broker, "client"):
            account = broker.client.get_account()
            return Decimal(str(account.equity))
        if hasattr(broker, "get_account"):
            account = broker.get_account()
            equity = (
                account.get("equity")
                if isinstance(account, dict)
                else getattr(account, "equity", None)
            )
            return Decimal(str(equity)) if equity is not None else None
    except Exception as e:
        logger.warning(f"Failed to fetch account equity: {e}")
    return None
