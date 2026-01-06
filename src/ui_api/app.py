"""FastAPI service for strategy dashboard.

This API provides read-only endpoints and safe edit endpoints for managing
multiple trading strategies. All configuration changes are staged (pending)
and activated at the start of the next trading loop tick.

IMPORTANT: This service is optional. The bot runs normally if the API is never started.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.app.ledger import Ledger
from src.app.strategy_registry import StrategyRegistry

# Global registry and ledger instances (initialized on startup)
registry: StrategyRegistry | None = None
ledger: Ledger | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize registry and ledger on startup."""
    global registry, ledger

    try:
        registry = StrategyRegistry()
        ledger = Ledger()
    except FileNotFoundError as e:
        # Registry or ledger not found - API will return errors
        print(f"WARNING: Failed to initialize registry or ledger: {e}")
        print("API endpoints will return errors until configuration is available")

    yield

    # Cleanup on shutdown (if needed)


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="AI Trader Strategy Dashboard",
    description="Read-only dashboard and safe configuration API for multi-strategy trading",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================================
# Request/Response Models
# ============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    registry_loaded: bool
    ledger_available: bool


class AccountSummaryResponse(BaseModel):
    """Account summary response."""

    total_capital: float
    max_daily_loss: float
    max_total_positions: int
    enabled_strategies_count: int
    total_strategies_count: int


class StrategyInfo(BaseModel):
    """Strategy information."""

    strategy_id: str
    name: str
    description: str
    enabled: bool
    weight: float
    params: dict[str, Any]
    risk_limits: dict[str, float | int]
    active_version: int
    pending_version: int | None
    last_modified: str | None


class StrategiesResponse(BaseModel):
    """Strategies list response."""

    strategies: list[StrategyInfo]
    global_config: dict[str, Any]


class ActivityEvent(BaseModel):
    """Activity event from ledger."""

    event_id: str
    timestamp: str
    event_type: str
    strategy_id: str | None
    details: dict[str, Any]


class ActivityResponse(BaseModel):
    """Recent activity response."""

    events: list[ActivityEvent]
    total_events: int


class EnableRequest(BaseModel):
    """Request to enable/disable a strategy."""

    enabled: bool


class WeightRequest(BaseModel):
    """Request to update strategy weight."""

    weight: float = Field(..., ge=0.0, le=1.0, description="Weight between 0.0 and 1.0")


class ParamsRequest(BaseModel):
    """Request to update strategy parameters."""

    params: dict[str, Any]


class ChangeResponse(BaseModel):
    """Response for configuration change."""

    success: bool
    message: str
    pending_version: int | None


class AllocationStrategyInfo(BaseModel):
    """Per-strategy allocation information."""

    strategy_id: str
    enabled: bool
    configured_weight: float
    normalized_weight: float
    budget: float
    utilization: float | None


class AllocationResponse(BaseModel):
    """Allocation status response."""

    equity_base: float | None
    timestamp: str
    strategies: list[AllocationStrategyInfo]
    mode: str  # "equity-based" or "legacy"


class CandidateInfo(BaseModel):
    """Candidate information."""

    symbol: str
    action: str
    confidence: float
    horizon: str
    expires_at: str | None
    sector: str | None
    tags: list[str]
    reason: str


class CandidatesResponse(BaseModel):
    """Candidates list response."""

    candidates: list[CandidateInfo]
    count: int
    last_generated: str | None


class DetailedHealthResponse(BaseModel):
    """Detailed health/readiness response."""

    status: str
    timestamp: str
    market_status: str  # "open" or "closed"
    last_loop_tick: str | None
    last_data_fetch_status: str | None
    last_error: str | None
    registry_loaded: bool
    ledger_available: bool
    single_instance_ok: bool
    trading_paused: bool


class PauseRequest(BaseModel):
    """Request to pause/resume trading."""

    paused: bool


class SelectorStatusResponse(BaseModel):
    """Selector status response."""

    last_run: str | None
    candidates_count: int
    candidates_by_action: dict[str, int]
    last_error: str | None


# ============================================================================
# GET Endpoints (Read-Only)
# ============================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns current status of the API service.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(UTC).isoformat(),
        registry_loaded=registry is not None and registry.state is not None,
        ledger_available=ledger is not None,
    )


@app.get("/account/summary", response_model=AccountSummaryResponse)
async def get_account_summary():
    """
    Get account summary.

    Returns overall account configuration and strategy counts.
    """
    if registry is None or registry.state is None:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    state = registry.get_state()
    enabled_count = len([s for s in state.strategies.values() if s.enabled])

    # Calculate total capital from global max positions notional
    # This is a proxy - in production you'd fetch from broker
    total_capital = state.global_config.max_total_positions * 1000.0  # Placeholder

    return AccountSummaryResponse(
        total_capital=total_capital,
        max_daily_loss=state.global_config.max_daily_loss,
        max_total_positions=state.global_config.max_total_positions,
        enabled_strategies_count=enabled_count,
        total_strategies_count=len(state.strategies),
    )


@app.get("/strategies", response_model=StrategiesResponse)
async def get_strategies():
    """
    Get all strategies.

    Returns list of all strategies with current configuration and status.
    """
    if registry is None or registry.state is None:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    state = registry.get_state()

    strategies_list = [
        StrategyInfo(
            strategy_id=strategy.strategy_id,
            name=strategy.name,
            description=strategy.description,
            enabled=strategy.enabled,
            weight=strategy.weight,
            params=strategy.params,
            risk_limits=strategy.risk_limits,
            active_version=strategy.active_version,
            pending_version=strategy.pending_version,
            last_modified=strategy.last_modified.isoformat() if strategy.last_modified else None,
        )
        for strategy in state.strategies.values()
    ]

    global_config = {
        "max_daily_loss": state.global_config.max_daily_loss,
        "max_total_positions": state.global_config.max_total_positions,
        "max_order_notional": state.global_config.max_order_notional,
        "bar_timeframe": state.global_config.bar_timeframe,
        "market_open_hour": state.global_config.market_open_hour,
        "market_open_minute": state.global_config.market_open_minute,
        "market_close_hour": state.global_config.market_close_hour,
        "market_close_minute": state.global_config.market_close_minute,
    }

    return StrategiesResponse(strategies=strategies_list, global_config=global_config)


@app.get("/activity", response_model=ActivityResponse)
async def get_activity(limit: int = 50):
    """
    Get recent activity.

    Returns recent events from the ledger (config changes, signals, orders, fills).

    Args:
        limit: Maximum number of events to return (default 50, max 200)
    """
    if ledger is None:
        raise HTTPException(status_code=503, detail="Ledger not available")

    # Cap limit at 200
    limit = min(limit, 200)

    # Read all events from today
    try:
        events = ledger.read_all(date=datetime.now(UTC).date())
    except Exception:
        # If no events today, return empty
        events = []

    # Convert to ActivityEvent format
    activity_events = []
    for event_dict in events[-limit:]:  # Get last N events
        activity_events.append(
            ActivityEvent(
                event_id=event_dict.get("event_id", ""),
                timestamp=event_dict.get("timestamp", ""),
                event_type=event_dict.get("event_type", ""),
                strategy_id=event_dict.get("strategy_id"),
                details={
                    k: v
                    for k, v in event_dict.items()
                    if k not in ["event_id", "timestamp", "event_type", "strategy_id"]
                },
            )
        )

    return ActivityResponse(events=activity_events, total_events=len(events))


# ============================================================================
# POST Endpoints (Safe Edit - Stage Changes for Next Tick)
# ============================================================================


@app.post("/strategies/{strategy_id}/enable", response_model=ChangeResponse)
async def update_strategy_enabled(strategy_id: str, request: EnableRequest):
    """
    Enable or disable a strategy.

    Changes are staged and will activate at the start of the next trading loop tick.

    Args:
        strategy_id: Strategy ID to modify
        request: Enable/disable request
    """
    if registry is None or registry.state is None:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    try:
        new_version = registry.stage_change(strategy_id, {"enabled": request.enabled})

        action = "enabled" if request.enabled else "disabled"
        return ChangeResponse(
            success=True,
            message=f"Strategy {strategy_id} {action}. Change will activate on next loop tick.",
            pending_version=new_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stage change: {e}") from e


@app.post("/strategies/{strategy_id}/weight", response_model=ChangeResponse)
async def update_strategy_weight(strategy_id: str, request: WeightRequest):
    """
    Update strategy weight.

    Weight determines capital allocation relative to other enabled strategies.
    Changes are staged and will activate at the start of the next trading loop tick.

    Args:
        strategy_id: Strategy ID to modify
        request: Weight update request (0.0 to 1.0)
    """
    if registry is None or registry.state is None:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    try:
        new_version = registry.stage_change(strategy_id, {"weight": request.weight})

        return ChangeResponse(
            success=True,
            message=f"Strategy {strategy_id} weight updated to {request.weight}. Change will activate on next loop tick.",
            pending_version=new_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stage change: {e}") from e


@app.post("/strategies/{strategy_id}/params", response_model=ChangeResponse)
async def update_strategy_params(strategy_id: str, request: ParamsRequest):
    """
    Update strategy parameters.

    Updates strategy-specific parameters (e.g., MA periods, thresholds).
    Changes are staged and will activate at the start of the next trading loop tick.

    Args:
        strategy_id: Strategy ID to modify
        request: Parameters update request
    """
    if registry is None or registry.state is None:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    try:
        new_version = registry.stage_change(strategy_id, {"params": request.params})

        return ChangeResponse(
            success=True,
            message=f"Strategy {strategy_id} parameters updated. Change will activate on next loop tick.",
            pending_version=new_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stage change: {e}") from e


# ============================================================================
# Ops Endpoints (Phase 4 - Dashboard Ops Controls)
# ============================================================================


@app.get("/allocation", response_model=AllocationResponse)
async def get_allocation():
    """
    Get current allocation status.

    Returns per-strategy allocation information including weights, budgets, and utilization.
    """
    if registry is None or registry.state is None:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    from src.app import allocation as alloc_module

    state = registry.get_state()
    enabled_strategies = [s for s in state.strategies.values() if s.enabled]

    # Compute normalized weights
    weight_summary = alloc_module.compute_weight_summary(enabled_strategies)

    # Build per-strategy allocation info
    strategies_info = []
    equity_base = None  # Would be fetched from broker in production

    for strategy in state.strategies.values():
        if strategy.enabled and strategy.strategy_id in weight_summary["normalized_weights"]:
            normalized_weight = weight_summary["normalized_weights"][strategy.strategy_id]
            budget = 0.0
            if equity_base:
                budget = alloc_module.compute_strategy_budget(equity_base, normalized_weight)

            strategies_info.append(
                AllocationStrategyInfo(
                    strategy_id=strategy.strategy_id,
                    enabled=strategy.enabled,
                    configured_weight=strategy.weight,
                    normalized_weight=normalized_weight,
                    budget=budget,
                    utilization=None,  # Would require position tracking
                )
            )
        else:
            strategies_info.append(
                AllocationStrategyInfo(
                    strategy_id=strategy.strategy_id,
                    enabled=strategy.enabled,
                    configured_weight=strategy.weight,
                    normalized_weight=0.0,
                    budget=0.0,
                    utilization=None,
                )
            )

    mode = "equity-based" if equity_base else "legacy"

    return AllocationResponse(
        equity_base=equity_base,
        timestamp=datetime.now(UTC).isoformat(),
        strategies=strategies_info,
        mode=mode,
    )


@app.get("/candidates", response_model=CandidatesResponse)
async def get_candidates():
    """
    Get current candidate list.

    Returns candidates loaded from the most recent snapshot.
    """
    import json

    snapshot_path = Path("out/selector/snapshot.json")

    if not snapshot_path.exists():
        return CandidatesResponse(candidates=[], count=0, last_generated=None)

    try:
        with open(snapshot_path, encoding="utf-8") as f:
            data = json.load(f)

        candidates_list = []
        for candidate in data.get("candidates", []):
            candidates_list.append(
                CandidateInfo(
                    symbol=candidate.get("symbol", ""),
                    action=candidate.get("action", ""),
                    confidence=candidate.get("confidence", 0.0),
                    horizon=candidate.get("horizon", ""),
                    expires_at=candidate.get("expires_at"),
                    sector=candidate.get("sector"),
                    tags=candidate.get("tags", []),
                    reason=candidate.get("reason", ""),
                )
            )

        return CandidatesResponse(
            candidates=candidates_list,
            count=len(candidates_list),
            last_generated=data.get("generated_at"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load candidates: {e}") from e


@app.get("/selector/status", response_model=SelectorStatusResponse)
async def get_selector_status():
    """Get selector status including last run time and candidate counts."""
    import json

    snapshot_path = Path("out/selector/snapshot.json")
    events_path = Path("out/selector/events.jsonl")

    last_run = None
    candidates_count = 0
    candidates_by_action = {"buy": 0, "sell": 0, "watch": 0}
    last_error = None

    # Read snapshot for candidate counts
    if snapshot_path.exists():
        try:
            with open(snapshot_path, encoding="utf-8") as f:
                data = json.load(f)

            last_run = data.get("generated_at")
            candidates_count = data.get("count", 0)

            # Count by action
            for candidate in data.get("candidates", []):
                action = candidate.get("action", "watch")
                if action in candidates_by_action:
                    candidates_by_action[action] += 1

        except Exception:
            pass

    # Check for last error in events
    if events_path.exists():
        try:
            with open(events_path, encoding="utf-8") as f:
                # Read last 10 lines to find most recent error
                lines = f.readlines()
                for line in reversed(lines[-10:]):
                    try:
                        event = json.loads(line)
                        if event.get("event_type") == "error":
                            last_error = event.get("error", "Unknown error")[:200]
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

    return SelectorStatusResponse(
        last_run=last_run,
        candidates_count=candidates_count,
        candidates_by_action=candidates_by_action,
        last_error=last_error,
    )


@app.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health():
    """
    Get detailed health and readiness status.

    Returns comprehensive system status including market hours, last tick, errors, etc.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Determine market status based on current ET time
    eastern = ZoneInfo("America/New_York")
    now_et = datetime.now(eastern)
    hour = now_et.hour
    minute = now_et.minute

    # Market hours: 9:30 AM - 4:00 PM ET
    is_market_open = (
        (hour == 9 and minute >= 30) or (10 <= hour < 16) or (hour == 16 and minute == 0)
    )
    market_status = "open" if is_market_open else "closed"

    # Check for last loop tick in status log
    last_loop_tick = None
    last_error = None

    status_log_path = Path("logs/loop_status.log")
    if status_log_path.exists():
        try:
            with open(status_log_path, encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    # Parse timestamp from log line format: [timestamp] STATUS | ...
                    if last_line.startswith("["):
                        end_bracket = last_line.find("]")
                        if end_bracket > 0:
                            last_loop_tick = last_line[1:end_bracket]
        except Exception:
            pass

    error_log_path = Path("logs/loop_errors.log")
    if error_log_path.exists():
        try:
            with open(error_log_path, encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_error = lines[-1].strip()[:200]  # Truncate to 200 chars
        except Exception:
            pass

    # Check if trading is paused
    pause_file = Path("state/pause_trading.flag")
    trading_paused = pause_file.exists()

    return DetailedHealthResponse(
        status="ok",
        timestamp=datetime.now(UTC).isoformat(),
        market_status=market_status,
        last_loop_tick=last_loop_tick,
        last_data_fetch_status=None,  # Would require tracking in runner
        last_error=last_error,
        registry_loaded=registry is not None and registry.state is not None,
        ledger_available=ledger is not None,
        single_instance_ok=True,  # Would require checking mutex
        trading_paused=trading_paused,
    )


@app.post("/pause_trading", response_model=ChangeResponse)
async def pause_trading(request: PauseRequest):
    """
    Pause or resume trading.

    This creates a pause flag file that the runner checks at the start of each tick.
    Changes apply at the next loop iteration.
    """
    pause_file = Path("state/pause_trading.flag")
    pause_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        if request.paused:
            # Create pause flag file
            with open(pause_file, "w", encoding="utf-8") as f:
                f.write(datetime.now(UTC).isoformat())

            return ChangeResponse(
                success=True,
                message="Trading paused. Orders will not be placed on next tick.",
                pending_version=None,
            )
        else:
            # Remove pause flag file
            if pause_file.exists():
                pause_file.unlink()

            return ChangeResponse(
                success=True,
                message="Trading resumed. Orders will be placed normally on next tick.",
                pending_version=None,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update pause state: {e}") from e


# ============================================================================
# HTML Dashboard (Phase 3)
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """
    Serve the HTML dashboard.

    Returns a self-contained single-page application with:
    - Account summary
    - Strategy cards with enable/disable toggles and weight sliders
    - Recent activity feed
    - Auto-refresh every 30 seconds
    """
    dashboard_path = Path(__file__).parent / "dashboard.html"

    try:
        with open(dashboard_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Dashboard not found</h1><p>dashboard.html is missing</p>",
            status_code=404,
        )
