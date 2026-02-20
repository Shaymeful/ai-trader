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
    rationales: dict[str, str] = Field(default_factory=dict, description="Ticker rationales")


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
    rationales: dict[str, str] = Field(default_factory=dict, description="Ticker rationales/descriptions")


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
        # Check for pending version and rationales
        pending_version = None
        rationales = {}
        if sector_name in universe_registry.overrides:
            override = universe_registry.overrides[sector_name]
            pending_version = override.pending_version
            rationales = override.rationales or {}

        sectors_list.append(
            SectorInfo(
                sector_name=sector_name,
                enabled=sector_config.enabled,
                description=sector_config.description,
                symbols=sector_config.symbols,
                symbol_count=len(sector_config.symbols),
                pending_version=pending_version,
                rationales=rationales,
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


@app.post("/universe/sectors/{sector_name}/exit-positions", response_model=ChangeResponse)
async def exit_sector_positions(sector_name: str):
    """
    Exit all open positions for tickers in a sector.

    Creates market sell orders for all open long positions in the sector.

    Args:
        sector_name: Sector name to exit positions for
    """
    if universe_registry is None:
        raise HTTPException(status_code=503, detail="Universe registry not loaded")

    try:
        # Create broker instance
        from src.app.config import load_config_with_yaml
        from src.broker.base import AlpacaBroker
        from src.app.models import OrderSide, OrderType
        import uuid

        config = load_config_with_yaml()
        broker = AlpacaBroker(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            trading_base_url=config.alpaca_trading_base_url,
        )

        # Get sector symbols
        if sector_name not in universe_registry.sectors:
            raise HTTPException(status_code=404, detail=f"Sector not found: {sector_name}")

        sector_symbols = set(universe_registry.sectors[sector_name].symbols)
        if not sector_symbols:
            raise HTTPException(status_code=400, detail="No symbols in sector")

        # Get open positions
        positions = broker.get_positions()
        sector_positions = {symbol: (qty, price) for symbol, (qty, price) in positions.items() if symbol in sector_symbols}

        if not sector_positions:
            return ChangeResponse(
                success=True,
                message=f"No open positions found for {sector_name} sector",
                pending_version=None,
            )

        # Submit market sell orders for each position
        exited_count = 0
        failed_count = 0
        for symbol, (qty, _) in sector_positions.items():
            if qty > 0:  # Only exit long positions
                try:
                    broker.submit_order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=qty,
                        client_order_id=f"exit-{sector_name}-{symbol}-{uuid.uuid4().hex[:8]}",
                        order_type=OrderType.MARKET,
                        limit_price=None,
                    )
                    exited_count += 1
                    print(f"Submitted market sell order for {symbol} (qty={qty})")
                except Exception as e:
                    print(f"Failed to exit position for {symbol}: {e}")
                    failed_count += 1

        if failed_count > 0:
            message = f"Exited {exited_count} positions for {sector_name} sector ({failed_count} failed)"
        else:
            message = f"Exited {exited_count} positions for {sector_name} sector"

        return ChangeResponse(
            success=True,
            message=message,
            pending_version=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to exit positions: {e}") from e


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

        # GUARD: Check if sector recommendations are enabled
        from src.app.llm_advisors.utils import is_sector_recommendations_enabled

        if not is_sector_recommendations_enabled(config):
            import logging

            logger = logging.getLogger("ai-trader.ui-api")
            logger.warning("Blocked sector proposal generation: sector_recommendations feature disabled")
            raise HTTPException(
                status_code=409,
                detail="Sector recommendations are currently disabled. Enable in AI Co-Pilot settings to generate proposals.",
            )

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
            # Filter rationales for only the tickers being added
            add_rationales = {t: request.rationales.get(t, "") for t in add_tickers if request.rationales.get(t)}
            pending_version = universe_registry.stage_constituent_change(
                sector_name, "add", add_tickers, rationales=add_rationales if add_rationales else None
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


@app.get("/config/bypass-capital-limit")
async def get_bypass_capital_limit():
    """Get the bypass capital limit setting."""
    try:
        ui_overrides_path = Path("data/ui_runtime_overrides.json")
        if ui_overrides_path.exists():
            with open(ui_overrides_path, "r") as f:
                overrides = json.load(f)
                bypass = overrides.get("allocator", {}).get("bypass_capital_limit", False)
                return {"bypass": bypass}
        return {"bypass": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load bypass setting: {e}") from e


@app.post("/config/bypass-capital-limit")
async def set_bypass_capital_limit(request: dict):
    """Set the bypass capital limit setting."""
    try:
        bypass = request.get("bypass", False)

        ui_overrides_path = Path("data/ui_runtime_overrides.json")
        overrides = {}

        if ui_overrides_path.exists():
            with open(ui_overrides_path, "r") as f:
                overrides = json.load(f)

        if "allocator" not in overrides:
            overrides["allocator"] = {}

        overrides["allocator"]["bypass_capital_limit"] = bypass
        overrides["allocator"]["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(ui_overrides_path, "w") as f:
            json.dump(overrides, f, indent=2)

        return {"success": True, "bypass": bypass}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save bypass setting: {e}") from e


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
# AI Co-Pilot Monitoring Routes
# ============================================================================


class AICopilotStatusResponse(BaseModel):
    """AI Co-Pilot status response."""

    timestamp: str
    enabled: bool
    influence_decisions: bool
    model: str
    budget: dict[str, Any]
    limits: dict[str, Any]
    features: dict[str, Any]
    errors: list[str]
    health: str


class AICopilotFeaturesResponse(BaseModel):
    """AI Co-Pilot features response."""

    trade_rationale: dict[str, Any]
    daily_journal: dict[str, Any]
    strategy_critique: dict[str, Any]


class AICopilotCritiqueResponse(BaseModel):
    """AI Co-Pilot critique history response."""

    critiques: list[dict[str, Any]]
    count: int


class AICopilotConfigUpdateRequest(BaseModel):
    """Request to update AI Co-Pilot configuration."""

    enabled: bool | None = Field(None, description="Enable/disable AI Co-Pilot")
    dry_run: bool | None = Field(None, description="Enable/disable dry-run mode")
    max_calls_per_run: int | None = Field(None, ge=0, description="Max LLM calls per run")
    budgets: dict[str, int] | None = Field(None, description="Budget limits")
    trade_rationale: dict[str, Any] | None = Field(None, description="Trade rationale settings")
    daily_journal: dict[str, Any] | None = Field(None, description="Daily journal settings")
    strategy_critique: dict[str, Any] | None = Field(None, description="Strategy critique settings")
    sector_recommendations: dict[str, Any] | None = Field(None, description="Sector recommendations settings")


@app.get("/api/ai-copilot/config")
async def get_ai_copilot_config():
    """
    Get AI Co-Pilot effective configuration with sources.

    Returns:
        Dict with "effective", "sources", and "trading_disabled_effective" keys
    """
    from src.app.config import load_config_with_yaml, load_yaml_config
    from src.app.llm_advisors.config_helpers import get_effective_config_with_sources

    config = load_config_with_yaml()
    yaml_config = load_yaml_config()

    return get_effective_config_with_sources(config, yaml_config)


@app.post("/api/ai-copilot/config")
async def update_ai_copilot_config(
    request: AICopilotConfigUpdateRequest,
    validate_only: bool = False,
):
    """
    Update AI Co-Pilot configuration via UI runtime overrides.

    Args:
        request: Configuration update request
        validate_only: If True, validate without writing (query param ?validate_only=1)

    Returns:
        Updated effective config with sources, or validation errors

    Safety:
        - Only allows safe fields (no influence_decisions, trading logic, etc.)
        - Validates all changes before applying
        - Atomic write (temp file → rename)
        - If trading disabled, enabled flag will remain false regardless
    """
    from src.app.llm_advisors.utils import (
        load_ui_runtime_overrides,
        save_ui_runtime_overrides,
        validate_ui_overrides,
    )

    # Load current overrides
    overrides = load_ui_runtime_overrides()

    # Ensure ai_copilot section exists
    if "ai_copilot" not in overrides:
        overrides["ai_copilot"] = {}

    # Update fields from request
    if request.enabled is not None:
        overrides["ai_copilot"]["enabled"] = request.enabled

    if request.dry_run is not None:
        overrides["ai_copilot"]["dry_run"] = request.dry_run

    if request.max_calls_per_run is not None:
        overrides["ai_copilot"]["max_calls_per_run"] = request.max_calls_per_run

    if request.budgets is not None:
        if "budgets" not in overrides["ai_copilot"]:
            overrides["ai_copilot"]["budgets"] = {}
        overrides["ai_copilot"]["budgets"].update(request.budgets)

    # Update feature settings
    for feature_name in ["trade_rationale", "daily_journal", "strategy_critique", "sector_recommendations"]:
        feature_data = getattr(request, feature_name, None)
        if feature_data is not None:
            if feature_name not in overrides["ai_copilot"]:
                overrides["ai_copilot"][feature_name] = {}
            overrides["ai_copilot"][feature_name].update(feature_data)

    # Add timestamp
    overrides["ai_copilot"]["updated_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z"

    # Validate overrides
    is_valid, errors = validate_ui_overrides(overrides)

    if not is_valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # If validate_only, return without writing
    if validate_only:
        return {
            "status": "valid",
            "message": "Configuration is valid (not saved)",
            "errors": [],
        }

    # Save overrides atomically
    success = save_ui_runtime_overrides(overrides)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # Reload config and return effective values
    from src.app.config import load_config_with_yaml, load_yaml_config
    from src.app.llm_advisors.config_helpers import get_effective_config_with_sources

    config = load_config_with_yaml()
    yaml_config = load_yaml_config()
    effective_data = get_effective_config_with_sources(config, yaml_config)

    return {
        "status": "success",
        "message": "Configuration updated. Changes will take effect on next loop iteration.",
        "effective": effective_data["effective"],
        "sources": effective_data["sources"],
    }


@app.get("/api/ai-copilot/status", response_model=AICopilotStatusResponse)
async def get_ai_copilot_status():
    """
    Get current AI Co-Pilot status.

    Returns:
        Status including enabled state, budget, features, and health
    """
    from src.app.llm_advisors.status import load_latest_status

    status = load_latest_status()

    if status is None:
        # Return default disabled status if no snapshot exists
        return AICopilotStatusResponse(
            timestamp=datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
            enabled=False,
            influence_decisions=False,
            model="gpt-4o-mini",
            budget={
                "max_calls_per_run": 3,
                "calls_used": 0,
                "calls_remaining": 3,
                "utilization_pct": 0.0,
            },
            limits={
                "max_output_tokens": 350,
                "timeout_s": 20,
            },
            features={
                "trade_rationale": {"enabled": False, "calls": 0, "successes": 0, "success_rate": 0.0},
                "daily_journal": {"enabled": False, "generated": False},
                "strategy_critique": {"enabled": False, "generated": False},
            },
            errors=[],
            health="unknown",
        )

    return AICopilotStatusResponse(**status)


@app.get("/api/ai-copilot/features", response_model=AICopilotFeaturesResponse)
async def get_ai_copilot_features():
    """
    Get AI Co-Pilot feature status.

    Returns:
        Feature-specific status and metrics
    """
    from src.app.llm_advisors.status import load_latest_status

    status = load_latest_status()

    if status is None or not status.get("features"):
        return AICopilotFeaturesResponse(
            trade_rationale={"enabled": False, "calls": 0, "successes": 0, "success_rate": 0.0},
            daily_journal={"enabled": False, "generated": False},
            strategy_critique={"enabled": False, "generated": False},
        )

    features = status["features"]
    return AICopilotFeaturesResponse(
        trade_rationale=features.get("trade_rationale", {}),
        daily_journal=features.get("daily_journal", {}),
        strategy_critique=features.get("strategy_critique", {}),
    )


@app.get("/api/ai-copilot/critique", response_model=AICopilotCritiqueResponse)
async def get_ai_copilot_critiques(limit: int = 5):
    """
    Get recent strategy critiques.

    Args:
        limit: Number of recent critiques to return (default 5)

    Returns:
        List of recent critiques (most recent first)
    """
    from src.app.llm_advisors.strategy_critique import load_recent_critiques

    critiques = load_recent_critiques(n=limit)

    return AICopilotCritiqueResponse(
        critiques=critiques,
        count=len(critiques),
    )


@app.get("/api/ai-copilot/history")
async def get_ai_copilot_history(limit: int = 50):
    """
    Get AI Co-Pilot run history.

    Args:
        limit: Maximum number of entries to return (default 50)

    Returns:
        List of run history entries (most recent first)
    """
    history_path = Path("logs/ai_copilot/run_history.jsonl")

    if not history_path.exists():
        return {
            "entries": [],
            "count": 0,
        }

    entries = []
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            for line in f:
                entries.append(json.loads(line.strip()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load history: {e}")

    # Return most recent entries first
    entries = entries[-limit:][::-1]

    return {
        "entries": entries,
        "count": len(entries),
    }


class AICopilotToggleRequest(BaseModel):
    """Request to toggle AI Co-Pilot master switch."""

    enabled: bool = Field(description="Enable or disable AI Co-Pilot")


class AICopilotFeatureToggleRequest(BaseModel):
    """Request to toggle individual AI Co-Pilot feature."""

    enabled: bool = Field(description="Enable or disable feature")


@app.post("/api/ai-copilot/toggle", response_model=ChangeResponse)
async def toggle_ai_copilot(request: AICopilotToggleRequest):
    """
    Toggle AI Co-Pilot master switch.

    SAFETY:
    - Changes are written to data/ui_runtime_overrides.json
    - Takes effect on next loop iteration
    - Does not affect running operations

    Args:
        request: Toggle request with enabled boolean

    Returns:
        Change confirmation
    """
    overrides_path = Path("data/ui_runtime_overrides.json")
    overrides_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing overrides
    overrides = {}
    if overrides_path.exists():
        try:
            with open(overrides_path, "r", encoding="utf-8") as f:
                overrides = json.load(f)
        except Exception:
            overrides = {}

    # Update AI Co-Pilot enabled flag
    if "ai_copilot" not in overrides:
        overrides["ai_copilot"] = {}

    overrides["ai_copilot"]["enabled"] = request.enabled
    overrides["ai_copilot"]["updated_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z"

    # Write overrides atomically
    temp_path = overrides_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    temp_path.replace(overrides_path)

    action = "enabled" if request.enabled else "disabled"
    return ChangeResponse(
        status="success",
        message=f"AI Co-Pilot {action}. Changes will take effect on next loop iteration.",
        details={"ai_copilot_enabled": request.enabled},
    )


@app.post("/api/ai-copilot/features/trade_rationale", response_model=ChangeResponse)
async def toggle_trade_rationale(request: AICopilotFeatureToggleRequest):
    """
    Toggle Trade Rationale feature.

    Args:
        request: Toggle request with enabled boolean

    Returns:
        Change confirmation
    """
    return _toggle_copilot_feature("trade_rationale", request.enabled)


@app.post("/api/ai-copilot/features/daily_journal", response_model=ChangeResponse)
async def toggle_daily_journal(request: AICopilotFeatureToggleRequest):
    """
    Toggle Daily Journal feature.

    Args:
        request: Toggle request with enabled boolean

    Returns:
        Change confirmation
    """
    return _toggle_copilot_feature("daily_journal", request.enabled)


@app.post("/api/ai-copilot/features/strategy_critique", response_model=ChangeResponse)
async def toggle_strategy_critique(request: AICopilotFeatureToggleRequest):
    """
    Toggle Strategy Critique feature.

    Args:
        request: Toggle request with enabled boolean

    Returns:
        Change confirmation
    """
    return _toggle_copilot_feature("strategy_critique", request.enabled)


def _toggle_copilot_feature(feature_name: str, enabled: bool) -> ChangeResponse:
    """
    Helper to toggle AI Co-Pilot feature.

    SAFETY:
    - Only modifies safe feature flags
    - Does not modify budget limits or influence_decisions flag
    - Changes take effect on next loop iteration

    Args:
        feature_name: Feature name (trade_rationale, daily_journal, strategy_critique)
        enabled: Enable or disable

    Returns:
        Change confirmation
    """
    overrides_path = Path("data/ui_runtime_overrides.json")
    overrides_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing overrides
    overrides = {}
    if overrides_path.exists():
        try:
            with open(overrides_path, "r", encoding="utf-8") as f:
                overrides = json.load(f)
        except Exception:
            overrides = {}

    # Update feature flag
    if "ai_copilot" not in overrides:
        overrides["ai_copilot"] = {}
    if "features" not in overrides["ai_copilot"]:
        overrides["ai_copilot"]["features"] = {}

    overrides["ai_copilot"]["features"][feature_name] = enabled
    overrides["ai_copilot"]["updated_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z"

    # Write overrides atomically
    temp_path = overrides_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    temp_path.replace(overrides_path)

    action = "enabled" if enabled else "disabled"
    return ChangeResponse(
        status="success",
        message=f"AI Co-Pilot feature '{feature_name}' {action}. Changes will take effect on next loop iteration.",
        details={f"{feature_name}_enabled": enabled},
    )


# ============================================================================
# Mode Switching (Aggressive Tech+Energy Daytrade Mode)
# ============================================================================


class ModeRequest(BaseModel):
    """Request to switch trading mode profile."""

    profile: Literal[
        "normal",
        "aggressive_tech_energy",
        "small_cap_swing",
        "aggressive_small_mid_sentiment",
    ] = Field(..., description="Mode profile to activate")


class ModeStatusResponse(BaseModel):
    """Mode status response."""

    active_profile: str
    available_profiles: list[str]
    profile_description: str
    coordinated_settings: dict[str, Any]


@app.post("/api/mode", response_model=ChangeResponse)
async def switch_mode(request: ModeRequest):
    """
    Switch trading mode profile.

    This endpoint coordinates changes across:
    - Strategy enable/weight/params (AI_COPILOT_WEIGHTED)
    - Universe sector toggles
    - Selector overrides
    - AI Co-Pilot feature flags

    Args:
        request: Mode switch request

    Returns:
        Change confirmation with pending versions
    """
    from src.app.config import load_mode_profiles, save_mode_override
    from src.app.selector_overrides import save_selector_overrides

    profile_name = request.profile

    # Load mode profiles
    modes_config = load_mode_profiles()
    profiles = modes_config.get("profiles", {})

    if profile_name not in profiles:
        raise HTTPException(
            status_code=400, detail=f"Unknown profile: {profile_name}. Available: {list(profiles.keys())}"
        )

    profile = profiles[profile_name]

    # SAFETY: Check if trading is paused
    pause_flag = Path("state/pause_trading.flag")
    if pause_flag.exists():
        return ChangeResponse(
            success=False,
            message=f"Trading is paused. Mode switch to '{profile_name}' saved but execution remains disabled.",
            pending_version=None,
        )

    # Save mode override
    if not save_mode_override(profile_name):
        raise HTTPException(status_code=500, detail="Failed to save mode override")

    pending_versions = []

    # 1. Apply strategy changes
    strategy_config = profile.get("strategies", {}).get("AI_COPILOT_WEIGHTED", {})
    if strategy_config and registry:
        strategy_id = "AI_COPILOT_WEIGHTED"

        # Enable/disable
        enabled = strategy_config.get("enabled", False)
        current_strategy = registry.get_strategy(strategy_id)
        current_enabled = current_strategy.enabled if current_strategy else False
        if enabled != current_enabled:
            new_version = registry.stage_change(strategy_id, {"enabled": enabled})
            if new_version:
                pending_versions.append(f"strategy_{strategy_id}_enable_v{new_version}")

        # Weight
        weight = strategy_config.get("weight")
        if weight is not None:
            new_version = registry.stage_change(strategy_id, {"weight": weight})
            if new_version:
                pending_versions.append(f"strategy_{strategy_id}_weight_v{new_version}")

        # Params (execution_enabled)
        params = strategy_config.get("params", {})
        if params:
            new_version = registry.stage_change(strategy_id, {"params": params})
            if new_version:
                pending_versions.append(f"strategy_{strategy_id}_params_v{new_version}")

    # 2. Apply universe sector changes
    universe_config = profile.get("universe", {}).get("sectors", {})
    if universe_config and universe_registry:
        for sector_name, enabled in universe_config.items():
            # Check current enabled status from sectors dict
            current_sector = universe_registry.sectors.get(sector_name)
            current_enabled = current_sector.enabled if current_sector else False
            if enabled != current_enabled:
                new_version = universe_registry.stage_change(sector_name, enabled)
                if new_version:
                    pending_versions.append(f"universe_{sector_name}_v{new_version}")

    # 3. Apply selector overrides
    selector_config = profile.get("selector", {})
    if selector_config:
        from src.app.selector_overrides import (
            get_aggressive_selector_overrides,
            get_normal_selector_overrides,
        )

        if profile_name == "aggressive_tech_energy":
            overrides = get_aggressive_selector_overrides()
        else:
            overrides = get_normal_selector_overrides()

        # Merge with custom selector config from profile
        overrides.update(selector_config)

        if not save_selector_overrides(profile_name, overrides):
            # Log warning but don't fail
            pass

    # 4. Apply AI Co-Pilot feature flags
    ai_copilot_config = profile.get("ai_copilot", {})
    if ai_copilot_config:
        overrides_path = Path("data/ui_runtime_overrides.json")
        overrides_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing overrides
        overrides = {}
        if overrides_path.exists():
            try:
                with open(overrides_path, "r", encoding="utf-8") as f:
                    overrides = json.load(f)
            except Exception:
                overrides = {}

        # Update AI Co-Pilot features
        if "ai_copilot" not in overrides:
            overrides["ai_copilot"] = {}

        for feature_name, enabled in ai_copilot_config.items():
            if feature_name not in overrides["ai_copilot"]:
                overrides["ai_copilot"][feature_name] = {}
            overrides["ai_copilot"][feature_name]["enabled"] = enabled

        overrides["ai_copilot"]["updated_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z"

        # Write overrides atomically
        temp_path = overrides_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=2)
        temp_path.replace(overrides_path)

    return ChangeResponse(
        success=True,
        message=f"Mode switched to '{profile_name}'. Changes will take effect on next loop iteration. Profile: {profile.get('description', '')} | Pending versions: {', '.join(pending_versions) if pending_versions else 'none'}",
        pending_version=len(pending_versions) if pending_versions else None,
    )


@app.get("/api/mode", response_model=ModeStatusResponse)
async def get_mode_status():
    """
    Get current mode status.

    Returns:
        Current active profile and available profiles
    """
    from src.app.config import get_active_mode_profile, load_mode_profiles

    modes_config = load_mode_profiles()
    profile_name, profile = get_active_mode_profile(modes_config)

    profiles = modes_config.get("profiles", {})

    return ModeStatusResponse(
        active_profile=profile_name,
        available_profiles=list(profiles.keys()),
        profile_description=profile.get("description", ""),
        coordinated_settings={
            "strategies": profile.get("strategies", {}),
            "universe": profile.get("universe", {}),
            "selector": profile.get("selector", {}),
            "ai_copilot": profile.get("ai_copilot", {}),
            "execution_gate": profile.get("execution_gate", {}),
        },
    )


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
