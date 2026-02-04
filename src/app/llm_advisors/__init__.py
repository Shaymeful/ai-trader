"""
AI Co-Pilot advisory layer.

SAFETY:
- Default OFF (config.ai_copilot_enabled = False)
- Never blocks loop (all failures are caught and logged)
- Advisory-only outputs (no branching unless config.ai_copilot_influence_decisions = True)
- Budget gates prevent runaway costs
"""

from src.app.llm_advisors.client import CoPilotClient
from src.app.llm_advisors.daily_journal import generate_daily_journal, should_generate_journal
from src.app.llm_advisors.status import StatusSnapshot, load_latest_status, write_run_summary
from src.app.llm_advisors.strategy_critique import (
    generate_strategy_critique,
    load_recent_critiques,
)
from src.app.llm_advisors.trade_rationale import (
    TradeRationaleResult,
    enrich_candidates_with_rationale,
    generate_trade_rationale,
)
from src.app.llm_advisors.universe_ticker_manager import (
    TickerAction,
    TickerManagerRecommendation,
    UniverseTickerManager,
)

__all__ = [
    "CoPilotClient",
    "generate_trade_rationale",
    "enrich_candidates_with_rationale",
    "TradeRationaleResult",
    "generate_daily_journal",
    "should_generate_journal",
    "generate_strategy_critique",
    "load_recent_critiques",
    "StatusSnapshot",
    "load_latest_status",
    "write_run_summary",
    "UniverseTickerManager",
    "TickerManagerRecommendation",
    "TickerAction",
]
