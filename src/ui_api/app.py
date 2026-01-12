"""FastAPI service for strategy dashboard.

This API provides read-only endpoints and safe edit endpoints for managing
multiple trading strategies. All configuration changes are staged (pending)
and activated at the start of the next trading loop tick.

IMPORTANT: This service is optional. The bot runs normally if the API is never started.
"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.app.ledger import Ledger
from src.app.strategy_registry import StrategyRegistry
from src.app.universe_registry import UniverseRegistry

# Global registry and ledger instances (initialized on startup)
registry: StrategyRegistry | None = None
ledger: Ledger | None = None
universe_registry: UniverseRegistry | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize registry and ledger on startup."""
    global registry, ledger, universe_registry

    try:
        registry = StrategyRegistry()
        ledger = Ledger()
    except FileNotFoundError as e:
        # Registry or ledger not found - API will return errors
        print(f"WARNING: Failed to initialize registry or ledger: {e}")
        print("API endpoints will return errors until configuration is available")

    # Initialize universe registry
    try:
        universe_registry = UniverseRegistry()
        print(f"Universe registry loaded: {len(universe_registry.sectors)} sectors")
    except FileNotFoundError as e:
        print(f"WARNING: Universe registry initialization failed: {e}")
        print("Universe endpoints will use base config only")
        universe_registry = None
    except Exception as e:
        print(f"ERROR: Failed to load universe registry: {e}")
        universe_registry = None

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


class RuntimeResponse(BaseModel):
    """Runtime state response with loop timing information."""

    loop_interval_seconds: int = Field(description="Configured loop interval in seconds")
    last_loop_start: str | None = Field(description="ISO timestamp of last loop start (UTC)")
    last_loop_end: str | None = Field(description="ISO timestamp of last loop end (UTC)")
    next_loop_at: str | None = Field(description="ISO timestamp of next scheduled loop (UTC)")
    seconds_until_next_loop: int | None = Field(
        description="Seconds until next loop (negative if overdue)"
    )
    updated_at: str = Field(description="ISO timestamp of state file update (UTC)")


class LoopIntervalRequest(BaseModel):
    """Request to update loop interval."""

    loop_interval_seconds: int = Field(
        description="New loop interval in seconds",
        ge=30,
        le=86400,
    )


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


class SectorEnableRequest(BaseModel):
    """Request to enable/disable a sector."""

    enabled: bool


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
    metadata: dict[str, Any] | None = None


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


class AdvisorRunInfo(BaseModel):
    """Advisor run information."""

    run_id: str
    advisor_type: str  # "universe_advisor" | "exit_advisor"
    started_at: str
    finished_at: str
    duration_seconds: float
    providers_used: list[str]
    model_name: str | None
    universe_size: int
    news_events_count: int
    market_regime: str | None
    raw_ideas_generated: int
    filtered_out: dict[str, int]
    final_proposals_count: int
    status: str  # "success" | "partial" | "error"
    error_message: str | None
    rationale_summary: list[str]


class AdvisorRunsResponse(BaseModel):
    """Advisor runs list response."""

    runs: list[AdvisorRunInfo]
    total_runs: int


class AdvisorPipelineStatus(BaseModel):
    """Pipeline status summary."""

    last_universe_run: str | None
    last_exit_run: str | None
    universe_evaluated: int
    universe_filtered_out: int
    universe_final: int
    exit_evaluated: int
    exit_filtered_out: int
    exit_final: int
    top_filter_reasons: dict[str, int]


class SectorInfo(BaseModel):
    """Sector information."""

    sector_name: str
    enabled: bool
    description: str
    symbols: list[str]
    symbol_count: int
    pending_version: int | None = None


class UniverseSectorsResponse(BaseModel):
    """Universe sectors response."""

    sectors: list[SectorInfo]
    resolved_symbols: list[str]
    total_symbols: int
    fallback_mode: str
    deduplication_count: int
    warnings: list[str]
    source: str


class ConstituentChangeResponse(BaseModel):
    """Constituent change details in a proposal."""

    action: str  # "add" or "remove"
    tickers: list[str]
    reason: str
    constraints_checked: bool = True


class ProposalResponse(BaseModel):
    """Single proposal response."""

    proposal_id: str
    sector_name: str
    confidence: float
    rationale: str
    supporting_headlines: list[str]
    provider: str
    created_at: str
    expires_at: str
    status: str
    proposal_type: str = "sector_toggle"  # "sector_toggle" or "constituent_change"
    # For SECTOR_TOGGLE proposals:
    recommended_enabled: bool | None = None
    # For CONSTITUENT_CHANGE proposals:
    constituent_change: ConstituentChangeResponse | None = None


class DisagreementResponse(BaseModel):
    """Provider disagreement response."""

    disagreement_id: str
    sector_name: str
    provider_a: str
    recommendation_a: bool
    confidence_a: float
    provider_b: str
    recommendation_b: bool
    confidence_b: float
    created_at: str


class ProposalsListResponse(BaseModel):
    """List of proposals and disagreements."""

    generation_id: str | None
    generated_at: str | None
    headline_count: int
    regime: dict[str, Any]
    proposals: list[ProposalResponse]
    disagreements: list[DisagreementResponse]
    filter_reasons: dict[str, list[str]] = Field(
        default_factory=dict, description="Sectors filtered by guardrails with reasons"
    )


class GenerateRequest(BaseModel):
    """Request to generate proposals."""

    force: bool = Field(default=False, description="Force generation even if recently generated")


class UpdateTickersRequest(BaseModel):
    """Request to update sector tickers."""

    add: list[str] = Field(default_factory=list, description="Tickers to add")
    remove: list[str] = Field(default_factory=list, description="Tickers to remove")


class CreateSectorRequest(BaseModel):
    """Request to create a new sector."""

    sector_name: str = Field(..., min_length=1, description="Sector name")
    description: str = Field(..., min_length=1, description="Sector description")
    symbols: list[str] = Field(default_factory=list, description="Initial symbols")
    enabled: bool = Field(default=False, description="Whether sector is enabled (default false)")


class CreateConstituentProposalRequest(BaseModel):
    """Request to create a constituent change proposal."""

    sector_name: str = Field(..., min_length=1, description="Target sector name")
    action: Literal["add", "remove"] = Field(..., description="Action to perform")
    tickers: list[str] = Field(..., min_items=1, description="Tickers to add/remove")
    source: str = Field(default="manual", description="Source of proposal (manual, candidates)")
    candidate_id: str | None = Field(default=None, description="Candidate ID if from candidates")
    rationale: str = Field(default="Operator-initiated change", description="Reason for change")


class AccountSummaryUpdateRequest(BaseModel):
    """Request to update account summary settings."""

    total_capital: float | None = Field(
        default=None, ge=1000.0, description="Total capital (>= $1000)"
    )
    max_daily_loss: float | None = Field(
        default=None, ge=100.0, description="Max daily loss (>= $100)"
    )
    max_total_positions: int | None = Field(
        default=None, ge=1, le=50, description="Max positions (1-50)"
    )


class AccountPerformanceResponse(BaseModel):
    """Account performance metrics."""

    equity: float | None = None
    last_equity: float | None = None
    cash: float | None = None
    buying_power: float | None = None
    day_pl: float | None = None
    day_pl_pct: float | None = None
    total_pl: float | None = None
    total_pl_pct: float | None = None
    data_source: str = "unavailable"
    message: str | None = None


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


@app.get("/runtime", response_model=RuntimeResponse)
async def get_runtime():
    """
    Get runtime state with loop timing information.

    Returns:
        - Configured loop interval
        - Last loop start/end times
        - Next scheduled loop time
        - Seconds until next loop (for countdown display)
    """
    from src.app.state import load_runtime_state

    runtime_state = load_runtime_state()

    # Calculate seconds until next loop
    seconds_until_next = None
    if runtime_state.next_loop_at:
        try:
            next_loop_dt = datetime.fromisoformat(runtime_state.next_loop_at.replace("Z", "+00:00"))
            now_utc = datetime.now(UTC)
            delta = (next_loop_dt - now_utc).total_seconds()
            seconds_until_next = int(delta)
        except Exception:
            pass

    return RuntimeResponse(
        loop_interval_seconds=runtime_state.loop_interval_seconds,
        last_loop_start=runtime_state.last_loop_start,
        last_loop_end=runtime_state.last_loop_end,
        next_loop_at=runtime_state.next_loop_at,
        seconds_until_next_loop=seconds_until_next,
        updated_at=runtime_state.updated_at,
    )


@app.post("/runtime/loop_interval", response_model=ChangeResponse)
async def update_loop_interval(request: LoopIntervalRequest):
    """
    Update loop interval.

    The new interval will be picked up by the runner on the next iteration.

    Args:
        request: Loop interval update request

    Returns:
        Success response
    """
    from src.app.state import load_runtime_state, save_runtime_state

    try:
        # Load current state
        runtime_state = load_runtime_state()

        # Update interval
        runtime_state.loop_interval_seconds = request.loop_interval_seconds

        # Save atomically
        save_runtime_state(runtime_state)

        return ChangeResponse(
            success=True,
            message=f"Loop interval updated to {request.loop_interval_seconds} seconds. Change will take effect on next iteration.",
            pending_version=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update loop interval: {e}") from e


@app.post("/runtime/trigger_loop", response_model=ChangeResponse)
async def trigger_loop_now():
    """
    Trigger the next loop iteration immediately.

    Creates a trigger flag file that the runner checks during sleep.
    The runner will wake up within 5 seconds and start the next iteration immediately.

    Returns:
        Success response
    """
    try:
        trigger_flag = Path("state/trigger_loop.flag")
        trigger_flag.parent.mkdir(parents=True, exist_ok=True)

        # Create trigger flag
        with open(trigger_flag, "w", encoding="utf-8") as f:
            f.write(datetime.now(UTC).isoformat())

        return ChangeResponse(
            success=True,
            message="Loop trigger sent. Next iteration will start within 5 seconds.",
            pending_version=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger loop: {e}") from e


@app.get("/account/summary", response_model=AccountSummaryResponse)
async def get_account_summary():
    """
    Get account summary.

    Returns overall account configuration and strategy counts.
    Priority: out/account_summary.json > registry config defaults.
    """
    if registry is None or registry.state is None:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    state = registry.get_state()
    enabled_count = len([s for s in state.strategies.values() if s.enabled])

    # Load from account_summary.json if exists, otherwise use config defaults
    settings_file = Path("out/account_summary.json")
    if settings_file.exists():
        try:
            with open(settings_file, encoding="utf-8") as f:
                settings = json.load(f)

            total_capital = settings.get(
                "total_capital", state.global_config.max_total_positions * 1000.0
            )
            max_daily_loss = settings.get("max_daily_loss", state.global_config.max_daily_loss)
            max_total_positions = settings.get(
                "max_total_positions", state.global_config.max_total_positions
            )
        except Exception:
            # Fall back to config defaults on error
            total_capital = state.global_config.max_total_positions * 1000.0
            max_daily_loss = state.global_config.max_daily_loss
            max_total_positions = state.global_config.max_total_positions
    else:
        # Use config defaults
        total_capital = state.global_config.max_total_positions * 1000.0
        max_daily_loss = state.global_config.max_daily_loss
        max_total_positions = state.global_config.max_total_positions

    return AccountSummaryResponse(
        total_capital=total_capital,
        max_daily_loss=max_daily_loss,
        max_total_positions=max_total_positions,
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
            metadata=data.get("metadata"),
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


@app.get("/advisor/runs", response_model=AdvisorRunsResponse)
async def get_advisor_runs(max_runs: int = 50):
    """Get recent advisor runs with telemetry."""
    from src.app.advisor_telemetry import AdvisorTelemetry

    try:
        telemetry = AdvisorTelemetry()
        runs_data = telemetry.read_recent_runs(max_runs=max_runs)

        runs = [AdvisorRunInfo(**run) for run in runs_data]

        return AdvisorRunsResponse(
            runs=runs,
            total_runs=len(runs),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load advisor runs: {e}") from e


@app.get("/advisor/status", response_model=AdvisorPipelineStatus)
async def get_advisor_pipeline_status():
    """Get advisor pipeline status summary."""
    from src.app.advisor_telemetry import AdvisorTelemetry

    try:
        telemetry = AdvisorTelemetry()
        runs = telemetry.read_recent_runs(max_runs=20)

        # Find last runs by type
        last_universe_run = None
        last_exit_run = None
        universe_stats = {"evaluated": 0, "filtered": 0, "final": 0}
        exit_stats = {"evaluated": 0, "filtered": 0, "final": 0}
        all_filters = {}

        for run in runs:
            advisor_type = run.get("advisor_type")
            if advisor_type == "universe_advisor" and not last_universe_run:
                last_universe_run = run.get("finished_at")
                universe_stats["evaluated"] = run.get("raw_ideas_generated", 0)
                universe_stats["filtered"] = sum(run.get("filtered_out", {}).values())
                universe_stats["final"] = run.get("final_proposals_count", 0)

                # Aggregate filter reasons
                for reason, count in run.get("filtered_out", {}).items():
                    all_filters[reason] = all_filters.get(reason, 0) + count

            elif advisor_type == "exit_advisor" and not last_exit_run:
                last_exit_run = run.get("finished_at")
                exit_stats["evaluated"] = run.get("raw_ideas_generated", 0)
                exit_stats["filtered"] = sum(run.get("filtered_out", {}).values())
                exit_stats["final"] = run.get("final_proposals_count", 0)

                # Aggregate filter reasons
                for reason, count in run.get("filtered_out", {}).items():
                    all_filters[reason] = all_filters.get(reason, 0) + count

        # Get top 3 filter reasons
        top_filters = dict(sorted(all_filters.items(), key=lambda x: x[1], reverse=True)[:3])

        return AdvisorPipelineStatus(
            last_universe_run=last_universe_run,
            last_exit_run=last_exit_run,
            universe_evaluated=universe_stats["evaluated"],
            universe_filtered_out=universe_stats["filtered"],
            universe_final=universe_stats["final"],
            exit_evaluated=exit_stats["evaluated"],
            exit_filtered_out=exit_stats["filtered"],
            exit_final=exit_stats["final"],
            top_filter_reasons=top_filters,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load pipeline status: {e}") from e


@app.get("/universe/sectors", response_model=UniverseSectorsResponse)
async def get_universe_sectors():
    """
    Get universe sectors and resolved symbol list.

    Returns sector configuration with operator overrides applied,
    resolved symbols, and deduplication info.
    """
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    # Resolve universe with current overrides
    resolution = universe_registry.resolve()

    # Build sector list with pending version indicators
    sectors_list = []
    for sector_name, sector_config in universe_registry.sectors.items():
        # Check for pending version
        pending_version = None
        if sector_name in universe_registry.overrides:
            override = universe_registry.overrides[sector_name]
            pending_version = override.pending_version

        sectors_list.append(
            SectorInfo(
                sector_name=sector_name,
                enabled=sector_config.enabled,
                description=sector_config.description,
                symbols=sector_config.symbols,
                symbol_count=len(sector_config.symbols),
                pending_version=pending_version,
            )
        )

    return UniverseSectorsResponse(
        sectors=sectors_list,
        resolved_symbols=resolution.symbols,
        total_symbols=len(resolution.symbols),
        fallback_mode="preserve_order",
        deduplication_count=resolution.deduplication_count,
        warnings=resolution.warnings,
        source=resolution.source,
    )


@app.post("/universe/sectors/{sector_name}/enable", response_model=ChangeResponse)
async def update_sector_enabled(sector_name: str, request: SectorEnableRequest):
    """
    Enable or disable a sector.

    Changes are staged and activate at the next loop tick.

    Args:
        sector_name: Sector name to modify
        request: Enable/disable request
    """
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    try:
        new_version = universe_registry.stage_change(sector_name, request.enabled)
        action = "enabled" if request.enabled else "disabled"
        return ChangeResponse(
            success=True,
            message=f"Sector {sector_name} {action}. Change will activate on next loop tick.",
            pending_version=new_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stage change: {e}") from e


@app.post("/universe/reset", response_model=ChangeResponse)
async def reset_universe():
    """Reset all sectors to default configuration.

    Clears all operator overrides and restores base config.
    """
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    try:
        universe_registry.reset_to_defaults()
        return ChangeResponse(
            success=True,
            message="Universe reset to defaults. All sectors enabled.",
            pending_version=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset universe: {e}") from e


@app.post("/universe/sectors", response_model=ChangeResponse)
async def create_sector(request: CreateSectorRequest):
    """Create a new sector (disabled by default).

    The sector is persisted to universe_overrides.json and requires explicit
    enabling before affecting trading.
    """
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    try:
        # Check if sector already exists
        if request.sector_name in universe_registry.sectors:
            raise HTTPException(
                status_code=400, detail=f"Sector '{request.sector_name}' already exists"
            )

        # Validate tickers (basic format check)
        for ticker in request.symbols:
            if not ticker or not ticker.isupper():
                raise HTTPException(status_code=400, detail=f"Invalid ticker format: {ticker}")

        # Create sector in UniverseRegistry
        from src.app.universe import SectorConfig

        new_sector = SectorConfig(
            name=request.sector_name,
            description=request.description,
            symbols=request.symbols,
            enabled=request.enabled,
        )
        universe_registry.sectors[request.sector_name] = new_sector

        # Create override entry (disabled by default unless explicitly enabled)
        from src.app.universe_registry import SectorOverride

        override = SectorOverride(
            enabled=request.enabled,
            active_version=1 if request.enabled else 0,
            pending_version=None,
            last_modified=datetime.now(UTC).isoformat(),
            tickers=request.symbols if request.symbols else None,
        )
        universe_registry.overrides[request.sector_name] = override

        # Save overrides atomically
        universe_registry._save_overrides()

        # Log to ledger
        if ledger:
            ledger.append(
                {
                    "event_type": "universe_sector_created",
                    "sector_name": request.sector_name,
                    "description": request.description,
                    "symbol_count": len(request.symbols),
                    "enabled": request.enabled,
                }
            )

        return ChangeResponse(
            success=True,
            message=f"Sector '{request.sector_name}' created with {len(request.symbols)} symbols. "
            + (
                "Enabled and active."
                if request.enabled
                else "Disabled by default - enable explicitly to trade."
            ),
            pending_version=override.active_version if request.enabled else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create sector: {e}") from e


@app.post("/universe/proposals/constituents", response_model=ChangeResponse)
async def create_constituent_proposal(request: CreateConstituentProposalRequest):
    """Create a constituent change proposal from candidate or manual action.

    Creates a gated proposal that requires operator approval before affecting trading.
    """
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    try:
        # Validate sector exists
        if request.sector_name not in universe_registry.sectors:
            raise HTTPException(status_code=404, detail=f"Sector '{request.sector_name}' not found")

        # Validate tickers
        for ticker in request.tickers:
            if not ticker or not ticker.isupper():
                raise HTTPException(status_code=400, detail=f"Invalid ticker format: {ticker}")

        # Get current sector symbols for validation
        sector = universe_registry.sectors[request.sector_name]
        current_symbols = set(sector.symbols)

        # Validation based on action
        if request.action == "add":
            already_present = [t for t in request.tickers if t in current_symbols]
            if already_present:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tickers already in sector: {', '.join(already_present)}",
                )
        elif request.action == "remove":
            not_present = [t for t in request.tickers if t not in current_symbols]
            if not_present:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tickers not in sector: {', '.join(not_present)}",
                )

        # Create proposal
        from src.app.universe_advisor.models import (
            ConstituentChange,
            ConstituentChangeAction,
            Proposal,
            ProposalType,
        )
        from src.app.universe_advisor.storage import load_proposals, save_proposals

        proposal_id = str(__import__("uuid").uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=24)  # 24h TTL for manual proposals

        constituent_change = ConstituentChange(
            action=ConstituentChangeAction(request.action),
            tickers=request.tickers,
            reason=request.rationale,
            constraints_checked=True,
        )

        proposal = Proposal(
            proposal_id=proposal_id,
            sector_name=request.sector_name,
            confidence=1.0,  # Manual proposals have full confidence
            rationale=request.rationale,
            supporting_headlines=[],
            provider="manual" if request.source == "manual" else request.source,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            status="NEW",
            proposal_type=ProposalType.CONSTITUENT_CHANGE,
            recommended_enabled=None,
            constituent_change=constituent_change,
        )

        # Load existing proposals
        proposals_file = Path("out/universe_proposals.json")
        existing_data = load_proposals(proposals_file)

        if existing_data:
            # Append to existing proposals list
            existing_data["proposals"].append(
                {
                    "proposal_id": proposal.proposal_id,
                    "sector_name": proposal.sector_name,
                    "confidence": proposal.confidence,
                    "rationale": proposal.rationale,
                    "supporting_headlines": proposal.supporting_headlines,
                    "provider": proposal.provider,
                    "created_at": proposal.created_at,
                    "expires_at": proposal.expires_at,
                    "status": proposal.status,
                    "proposal_type": proposal.proposal_type.value,
                    "recommended_enabled": proposal.recommended_enabled,
                    "constituent_change": {
                        "action": constituent_change.action.value,
                        "tickers": constituent_change.tickers,
                        "reason": constituent_change.reason,
                        "constraints_checked": constituent_change.constraints_checked,
                    },
                }
            )

            # Save atomically
            from src.app.universe_advisor.apply import save_proposals_dict

            save_proposals_dict(existing_data, proposals_file)
        else:
            # Create new proposals file with this single proposal
            from src.app.universe_advisor.models import MarketRegime, ProposalSet, RegimeData
            from src.app.universe_advisor.storage import save_proposals

            # Create minimal regime data
            regime = RegimeData(
                regime=MarketRegime.UNKNOWN,
                spy_price=0.0,
                spy_ma50=0.0,
                trend="bull",
                volatility="low",
                volatility_value=0.0,
                confidence=0.0,
                timestamp=now.isoformat(),
            )

            proposal_set = ProposalSet(
                generation_id=str(__import__("uuid").uuid4()),
                proposals=[proposal],
                disagreements=[],
                regime=regime,
                headline_count=0,
                generated_at=now.isoformat(),
            )

            save_proposals(proposal_set, proposals_file, filter_reasons={})

        # Log to ledger
        if ledger:
            ledger.append(
                {
                    "event_type": "universe_proposal_created_from_candidate"
                    if request.source == "candidates"
                    else "universe_proposal_created_manual",
                    "proposal_id": proposal_id,
                    "sector_name": request.sector_name,
                    "action": request.action,
                    "tickers": request.tickers,
                    "source": request.source,
                    "candidate_id": request.candidate_id,
                }
            )

        return ChangeResponse(
            success=True,
            message=f"Proposal created to {request.action.upper()} "
            + f"{len(request.tickers)} ticker(s) to/from {request.sector_name}. "
            + "Awaiting approval.",
            pending_version=None,  # No pending version until approved
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create proposal: {e}") from e


@app.get("/universe/proposal-history")
async def get_proposals_history(limit: int = 50):
    """Get proposal history from history file."""
    import json

    history_file = Path("out/universe_proposals_history.jsonl")

    if not history_file.exists():
        return {"history": []}

    try:
        history = []
        with open(history_file, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    history.append(entry)
                except json.JSONDecodeError:
                    continue

        # Return most recent entries first
        history.reverse()

        return {"history": history[:limit]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load history: {e}") from e


@app.get("/universe/proposals", response_model=ProposalsListResponse)
async def get_proposals():
    """Get current proposals and disagreements."""
    from src.app.universe_advisor.storage import load_proposals

    proposals_file = Path("out/universe_proposals.json")
    data = load_proposals(proposals_file)

    if not data:
        return ProposalsListResponse(
            generation_id=None,
            generated_at=None,
            headline_count=0,
            regime={},
            proposals=[],
            disagreements=[],
            filter_reasons={},
        )

    # Convert to response models
    proposals = [ProposalResponse(**p) for p in data.get("proposals", [])]
    disagreements = [DisagreementResponse(**d) for d in data.get("disagreements", [])]
    filter_reasons = data.get("filter_reasons", {})

    return ProposalsListResponse(
        generation_id=data.get("generation_id"),
        generated_at=data.get("generated_at"),
        headline_count=data.get("headline_count", 0),
        regime=data.get("regime", {}),
        proposals=proposals,
        disagreements=disagreements,
        filter_reasons=filter_reasons,
    )


@app.post("/universe/proposals/generate", response_model=ChangeResponse)
async def generate_proposals_endpoint(request: GenerateRequest):
    """Generate new proposals manually."""
    from src.app.config import load_config_with_yaml, load_yaml_config
    from src.app.data_providers.hourly_provider import HourlyMarketDataProvider
    from src.app.universe import load_universe_config
    from src.app.universe_advisor.generate import (
        generate_proposals,
        load_recent_rss_events,
    )
    from src.app.universe_advisor.guardrails import apply_guardrails
    from src.app.universe_advisor.regime import detect_market_regime
    from src.app.universe_advisor.storage import load_proposals, save_proposals

    try:
        config = load_config_with_yaml()

        # Check if recently generated (unless force=True)
        if not request.force:
            proposals_file = Path("out/universe_proposals.json")
            existing = load_proposals(proposals_file)
            if existing:
                generated_at = datetime.fromisoformat(existing.get("generated_at", ""))
                elapsed_hours = (datetime.now(UTC) - generated_at).total_seconds() / 3600
                if elapsed_hours < config.llm_auto_generate_interval_hours:
                    return ChangeResponse(
                        success=False,
                        message=f"Proposals generated {elapsed_hours:.1f}h ago. Use force=true to regenerate.",
                        pending_version=None,
                    )

        # Detect regime
        provider = HourlyMarketDataProvider(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
        )
        regime = detect_market_regime(provider)

        # Load RSS events
        events_file = Path("out/selector/events.jsonl")
        events = load_recent_rss_events(
            events_file,
            lookback_hours=config.llm_rss_lookback_hours,
            max_headlines=config.llm_rss_max_headlines,
        )

        # Load sectors
        yaml_config = load_yaml_config()
        universe_config = load_universe_config(yaml_config)
        sectors = {
            name: {"description": sec.description, "symbols": sec.symbols}
            for name, sec in universe_config.sectors.items()
        }

        # Generate proposals
        llm_config = {
            "mode": config.llm_mode,
            "primary": config.llm_primary,
            "openai_model": config.llm_openai_model,
            "anthropic_model": config.llm_anthropic_model,
            "timeout": config.llm_timeout,
        }

        history_file = Path("out/universe_proposals_history.jsonl")

        # Generate proposals (with telemetry disabled - we'll log after guardrails)
        proposal_set = generate_proposals(
            llm_config,
            regime,
            events,
            sectors,
            config.llm_proposal_ttl_minutes,
            enable_telemetry=False,
        )

        # Track pre-guardrail count for telemetry
        pre_guardrail_count = len(proposal_set.proposals)

        # Apply guardrails
        guardrails_config = {
            "min_confidence": config.llm_min_confidence,
            "max_sector_toggles_per_day": config.llm_max_sector_toggles_per_day,
            "cooldown_days": config.llm_cooldown_days,
        }
        proposal_set, filter_reasons = apply_guardrails(
            proposal_set, guardrails_config, history_file
        )

        # Log telemetry AFTER guardrails (so counts are accurate)
        from src.app.advisor_telemetry import AdvisorTelemetry, create_telemetry_context

        provider_mode = config.llm_mode
        provider_names = []
        if provider_mode == "ensemble":
            provider_names = ["openai", "anthropic"]
        else:
            provider_names = [config.llm_primary]

        telemetry_context = create_telemetry_context(
            advisor_type="universe_advisor",
            providers=provider_names,
            model_name=config.llm_openai_model or config.llm_anthropic_model,
            universe_size=len(sectors),
            news_count=len(events),
            regime=regime.regime.value,
        )

        telemetry_context.add_raw_ideas(pre_guardrail_count)

        # Add filtering details
        if filter_reasons:
            for _sector_name, reasons in filter_reasons.items():
                for reason in reasons:
                    # Extract filter category from reason string
                    if "confidence" in reason.lower():
                        telemetry_context.add_filtered("confidence_too_low", 1)
                    elif "cooldown" in reason.lower():
                        telemetry_context.add_filtered("cooldown", 1)
                    elif "max toggles" in reason.lower():
                        telemetry_context.add_filtered("max_toggles_per_day", 1)
                    elif "expired" in reason.lower():
                        telemetry_context.add_filtered("expired", 1)

        telemetry_context.set_final_count(len(proposal_set.proposals))

        if proposal_set.proposals:
            telemetry_context.add_rationale(
                f"Generated {len(proposal_set.proposals)} sector proposals from {len(events)} news events"
            )
        else:
            if filter_reasons:
                filtered_sectors = ", ".join(filter_reasons.keys())
                telemetry_context.add_rationale(
                    f"All {pre_guardrail_count} proposals filtered: {filtered_sectors}"
                )
            else:
                telemetry_context.add_rationale("No proposals met criteria")

        event = telemetry_context.finalize()
        AdvisorTelemetry().log_run(event)

        # Save (with filter reasons for UI display)
        proposals_file = Path("out/universe_proposals.json")
        save_proposals(proposal_set, proposals_file, filter_reasons)

        # Log to ledger
        if ledger:
            ledger.append(
                {
                    "event_type": "universe_proposals_generated",
                    "generation_id": proposal_set.generation_id,
                    "proposal_count": len(proposal_set.proposals),
                    "disagreement_count": len(proposal_set.disagreements),
                    "filtered_count": len(filter_reasons),
                    "regime": regime.regime.value,
                    "headline_count": len(events),
                }
            )

        # Build message
        message_parts = [f"Generated {len(proposal_set.proposals)} proposals"]
        if len(proposal_set.disagreements) > 0:
            message_parts.append(f"{len(proposal_set.disagreements)} disagreements")
        if filter_reasons:
            filtered_sectors = ", ".join(filter_reasons.keys())
            message_parts.append(f"Filtered {len(filter_reasons)} sectors: {filtered_sectors}")

        return ChangeResponse(
            success=True,
            message=", ".join(message_parts) + ".",
            pending_version=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate proposals: {e}") from e


@app.post("/universe/proposals/{proposal_id}/approve", response_model=ChangeResponse)
async def approve_proposal(proposal_id: str):
    """Approve a proposal and stage UniverseRegistry change."""
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    from src.app.universe_advisor.apply import apply_proposal
    from src.app.universe_advisor.models import Proposal
    from src.app.universe_advisor.storage import load_proposals

    try:
        proposals_file = Path("out/universe_proposals.json")
        data = load_proposals(proposals_file)

        if not data:
            raise HTTPException(status_code=404, detail="No proposals found")

        # Find proposal
        proposal_data = None
        for p in data.get("proposals", []):
            if p["proposal_id"] == proposal_id:
                proposal_data = p
                break

        if not proposal_data:
            raise HTTPException(status_code=404, detail="Proposal not found")

        if proposal_data["status"] != "NEW":
            raise HTTPException(
                status_code=400, detail=f"Proposal status is {proposal_data['status']}"
            )

        # Convert to Proposal object
        from src.app.universe_advisor.models import (
            ConstituentChange,
            ConstituentChangeAction,
            ProposalType,
        )

        # Handle constituent_change if present
        constituent_change = None
        if (
            proposal_data.get("proposal_type") == "constituent_change"
            and "constituent_change" in proposal_data
        ):
            cc_data = proposal_data["constituent_change"]
            constituent_change = ConstituentChange(
                action=ConstituentChangeAction(cc_data["action"]),
                tickers=cc_data["tickers"],
                reason=cc_data["reason"],
                constraints_checked=cc_data["constraints_checked"],
            )

        proposal = Proposal(
            proposal_id=proposal_data["proposal_id"],
            sector_name=proposal_data["sector_name"],
            confidence=proposal_data["confidence"],
            rationale=proposal_data["rationale"],
            supporting_headlines=proposal_data["supporting_headlines"],
            provider=proposal_data["provider"],
            created_at=proposal_data["created_at"],
            expires_at=proposal_data["expires_at"],
            status=proposal_data["status"],
            proposal_type=ProposalType(proposal_data.get("proposal_type", "sector_toggle")),
            recommended_enabled=proposal_data.get("recommended_enabled"),
            constituent_change=constituent_change,
        )

        # Apply (stages UniverseRegistry change)
        history_file = Path("out/universe_proposals_history.jsonl")
        new_version = apply_proposal(proposal, universe_registry, proposals_file, history_file)

        # Build message based on proposal type
        if proposal.proposal_type == ProposalType.SECTOR_TOGGLE:
            message = f"Proposal approved. {proposal.sector_name} will be {'enabled' if proposal.recommended_enabled else 'disabled'} on next loop tick."
        elif (
            proposal.proposal_type == ProposalType.CONSTITUENT_CHANGE
            and proposal.constituent_change
        ):
            action_str = proposal.constituent_change.action.value.upper()
            tickers_str = ", ".join(proposal.constituent_change.tickers)
            message = f"Proposal approved. Will {action_str} {tickers_str} to/from {proposal.sector_name} on next loop tick."
        else:
            message = "Proposal approved."

        # Log to ledger
        if ledger:
            log_entry = {
                "event_type": "universe_proposal_approved",
                "proposal_id": proposal_id,
                "sector_name": proposal.sector_name,
                "proposal_type": proposal.proposal_type.value,
                "pending_version": new_version,
            }
            if proposal.proposal_type == ProposalType.SECTOR_TOGGLE:
                log_entry["recommended_enabled"] = proposal.recommended_enabled
            elif (
                proposal.proposal_type == ProposalType.CONSTITUENT_CHANGE
                and proposal.constituent_change
            ):
                log_entry["constituent_change"] = {
                    "action": proposal.constituent_change.action.value,
                    "tickers": proposal.constituent_change.tickers,
                }
            ledger.append(log_entry)

        return ChangeResponse(
            success=True,
            message=message,
            pending_version=new_version,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve proposal: {e}") from e


@app.post("/universe/proposals/{proposal_id}/reject", response_model=ChangeResponse)
async def reject_proposal(proposal_id: str):
    """Reject a proposal."""
    from src.app.universe_advisor.apply import save_proposals_dict
    from src.app.universe_advisor.models import Proposal
    from src.app.universe_advisor.storage import append_to_history, load_proposals

    try:
        proposals_file = Path("out/universe_proposals.json")
        data = load_proposals(proposals_file)

        if not data:
            raise HTTPException(status_code=404, detail="No proposals found")

        # Find and update proposal
        found = False
        proposal_data = None
        for p in data.get("proposals", []):
            if p["proposal_id"] == proposal_id:
                p["status"] = "REJECTED"
                proposal_data = p
                found = True
                break

        if not found:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Save directly as dict (atomic write)
        save_proposals_dict(data, proposals_file)

        # Reconstruct Proposal object for history (with enum conversions)
        from src.app.universe_advisor.models import (
            ConstituentChange,
            ConstituentChangeAction,
            ProposalType,
        )

        constituent_change = None
        if (
            proposal_data.get("proposal_type") == "constituent_change"
            and "constituent_change" in proposal_data
        ):
            cc_data = proposal_data["constituent_change"]
            constituent_change = ConstituentChange(
                action=ConstituentChangeAction(cc_data["action"]),
                tickers=cc_data["tickers"],
                reason=cc_data["reason"],
                constraints_checked=cc_data["constraints_checked"],
            )

        proposal = Proposal(
            proposal_id=proposal_data["proposal_id"],
            sector_name=proposal_data["sector_name"],
            confidence=proposal_data["confidence"],
            rationale=proposal_data["rationale"],
            supporting_headlines=proposal_data["supporting_headlines"],
            provider=proposal_data["provider"],
            created_at=proposal_data["created_at"],
            expires_at=proposal_data["expires_at"],
            status=proposal_data["status"],
            proposal_type=ProposalType(proposal_data.get("proposal_type", "sector_toggle")),
            recommended_enabled=proposal_data.get("recommended_enabled"),
            constituent_change=constituent_change,
        )

        history_file = Path("out/universe_proposals_history.jsonl")
        append_to_history(proposal, "REJECTED", history_file)

        # Log to ledger
        if ledger:
            ledger.append(
                {
                    "event_type": "universe_proposal_rejected",
                    "proposal_id": proposal_id,
                    "sector_name": proposal.sector_name,
                }
            )

        return ChangeResponse(
            success=True,
            message="Proposal rejected.",
            pending_version=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject proposal: {e}") from e


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


@app.post("/universe/sectors/{sector_name}/tickers", response_model=ChangeResponse)
async def update_sector_tickers(sector_name: str, request: UpdateTickersRequest):
    """
    Manually add or remove tickers from a sector.

    This is an operator-gated action that stages changes via UniverseRegistry.
    Changes require activation (pending_version increment).
    """
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    if ledger is None:
        raise HTTPException(status_code=503, detail="Ledger not available")

    # Validate sector exists
    if sector_name not in universe_registry.sectors:
        raise HTTPException(status_code=404, detail=f"Sector not found: {sector_name}")

    # Validate request has at least one action
    if not request.add and not request.remove:
        raise HTTPException(status_code=400, detail="Must specify tickers to add or remove")

    # Normalize tickers (uppercase, dedupe)
    add_tickers = list(set(t.upper().strip() for t in request.add if t.strip()))
    remove_tickers = list(set(t.upper().strip() for t in request.remove if t.strip()))

    # Check for overlap
    overlap = set(add_tickers) & set(remove_tickers)
    if overlap:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add and remove same tickers: {', '.join(overlap)}",
        )

    try:
        # Stage changes - add first, then remove
        warnings = []
        pending_version = None

        if add_tickers:
            pending_version = universe_registry.stage_constituent_change(
                sector_name, "add", add_tickers
            )

        if remove_tickers:
            pending_version = universe_registry.stage_constituent_change(
                sector_name, "remove", remove_tickers
            )

        # Log to ledger
        ledger.append(
            {
                "event_type": "manual_sector_tickers_staged",
                "sector_name": sector_name,
                "add": add_tickers,
                "remove": remove_tickers,
                "pending_version": pending_version,
                "actor": "operator_ui",
            }
        )

        # Check tradability (best effort - warn if unavailable)
        try:
            from src.app.config import load_config_with_yaml
            from src.broker.base import AlpacaBroker

            config = load_config_with_yaml()
            broker = AlpacaBroker(
                api_key=config.alpaca_api_key,
                secret_key=config.alpaca_secret_key,
                trading_base_url=config.alpaca_trading_base_url,
            )

            for ticker in add_tickers:
                if not broker.is_asset_tradable(ticker):
                    warnings.append(f"{ticker} may not be tradable")
        except Exception as e:
            warnings.append(f"Could not verify tradability: {e}")

        # Build message
        msg_parts = []
        if add_tickers:
            msg_parts.append(f"Added {len(add_tickers)} ticker(s)")
        if remove_tickers:
            msg_parts.append(f"Removed {len(remove_tickers)} ticker(s)")
        msg = f"{', '.join(msg_parts)} to {sector_name}. Changes staged (v{pending_version})."

        if warnings:
            msg += f" Warnings: {'; '.join(warnings)}"

        return ChangeResponse(
            success=True,
            message=msg,
            pending_version=pending_version,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update tickers: {e}") from e


@app.post("/account/summary", response_model=ChangeResponse)
async def update_account_summary(request: AccountSummaryUpdateRequest):
    """
    Update account summary settings (total capital, max daily loss, max positions).

    Settings are persisted to out/account_summary.json and applied to registry at runtime.
    """
    if ledger is None:
        raise HTTPException(status_code=503, detail="Ledger not available")
    if registry is None:
        raise HTTPException(status_code=503, detail="Registry not available")

    # Load existing settings
    settings_file = Path("out/account_summary.json")
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    if settings_file.exists():
        try:
            with open(settings_file, encoding="utf-8") as f:
                current_settings = json.load(f)
        except Exception:
            current_settings = {}
    else:
        current_settings = {}

    # Apply updates (only non-None fields)
    old_settings = current_settings.copy()
    updated_fields = []
    registry_changes = {}

    if request.total_capital is not None:
        current_settings["total_capital"] = request.total_capital
        updated_fields.append("total_capital")
        # Note: total_capital is display-only, not part of registry config

    if request.max_daily_loss is not None:
        current_settings["max_daily_loss"] = request.max_daily_loss
        updated_fields.append("max_daily_loss")
        registry_changes["max_daily_loss"] = request.max_daily_loss

    if request.max_total_positions is not None:
        current_settings["max_total_positions"] = request.max_total_positions
        updated_fields.append("max_total_positions")
        registry_changes["max_total_positions"] = request.max_total_positions

    if not updated_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Save atomically
    try:
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=settings_file.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            json.dump(current_settings, tmp_file, indent=2)
            tmp_path = Path(tmp_file.name)

        tmp_path.replace(settings_file)

        # Update registry with runtime changes (if any)
        if registry_changes:
            try:
                registry.stage_global_config_change(registry_changes)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid values: {e}") from e

        # Log to ledger
        ledger.append(
            {
                "event_type": "account_summary_updated",
                "old_settings": old_settings,
                "new_settings": current_settings,
                "updated_fields": updated_fields,
                "actor": "operator_ui",
            }
        )

        return ChangeResponse(
            success=True,
            message=f"Updated {', '.join(updated_fields)} (effective immediately)",
            pending_version=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}") from e


@app.get("/account/performance", response_model=AccountPerformanceResponse)
async def get_account_performance():
    """
    Get account performance metrics from broker (if available).

    Returns P&L data for current day and overall totals.
    """
    try:
        from src.app.config import load_config_with_yaml

        config = load_config_with_yaml()

        # Try to fetch from Alpaca
        # Get broker instance (AlpacaBroker works for both paper and live)
        from src.broker.base import AlpacaBroker

        broker = AlpacaBroker(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            trading_base_url=config.alpaca_trading_base_url,
        )

        # Get account info from Alpaca API
        account = broker.client.get_account()

        equity = float(account.equity)
        last_equity = float(account.last_equity)
        cash = float(account.cash)
        buying_power = float(account.buying_power)

        # Calculate day P&L
        day_pl = equity - last_equity
        day_pl_pct = (day_pl / last_equity * 100) if last_equity > 0 else 0.0

        # Total P&L (if initial equity known, else just show current equity)
        # For now, we don't track initial equity, so total_pl is unavailable
        total_pl = None
        total_pl_pct = None

        # Capture equity snapshot (best-effort)
        try:
            from src.app.equity_capture import capture_equity_snapshot

            capture_equity_snapshot(
                equity=equity,
                cash=cash,
                mode=config.mode,
            )
        except Exception as e:
            print(f"WARNING: Failed to capture equity snapshot: {e}")

        return AccountPerformanceResponse(
            equity=equity,
            last_equity=last_equity,
            cash=cash,
            buying_power=buying_power,
            day_pl=day_pl,
            day_pl_pct=day_pl_pct,
            total_pl=total_pl,
            total_pl_pct=total_pl_pct,
            data_source=config.mode,
            message=None,
        )

    except Exception as e:
        # Return placeholder data if broker unavailable
        return AccountPerformanceResponse(
            equity=None,
            last_equity=None,
            cash=None,
            buying_power=None,
            day_pl=None,
            day_pl_pct=None,
            total_pl=None,
            total_pl_pct=None,
            data_source="unavailable",
            message=f"Broker data unavailable: {e}",
        )


@app.get("/account/performance/series")
async def get_equity_series(hours: int = 24):
    """
    Get equity time series for the last N hours.

    Args:
        hours: Time window in hours (default: 24, max: 720 = 30 days)

    Returns:
        List of equity snapshots with timestamp, equity, cash, mode
    """
    from pathlib import Path

    from src.app.equity_capture import load_equity_series

    # Cap hours at 30 days
    hours = min(hours, 720)

    equity_file = Path("out/perf/equity.jsonl")
    points = load_equity_series(equity_file, hours=hours)

    return {
        "points": points,
        "count": len(points),
        "hours": hours,
    }


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
