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
