# Changelog

All notable changes to AI-Trader will be documented in this file.

## 2026-02-18 - Market Hours Checking

### Changed
- **Loop Mode Market Hours**: Loop now automatically checks market hours before each iteration
  - Skips execution when market is closed (nights, weekends, holidays)
  - Sleeps until next market open (Monday-Friday, 9:30 AM - 4:00 PM ET)
  - Prevents unnecessary market data fetching and strategy execution outside trading hours
  - Manual override: Create `state/trigger_loop.flag` file to force immediate wake-up (useful for testing)
  - No configuration required - market hours checking is always enabled

### Technical
- Added market hours checking in `src/app/runner.py:run_loop()` using existing `market_hours.py` utilities
- Loop uses 60-second check intervals during closed periods (faster response to manual triggers)
- Keyboard interrupt (Ctrl+C) works during market closed sleep periods

## 2026-01-06 - Universe Advisor

### Added
- **LLM-Powered Universe Advisor**: Operator-gated decision-support system for sector recommendations
  - Analyzes market regime (SPY trend + volatility) and recent news to generate sector enable/disable proposals
  - All proposals require explicit operator approval via dashboard before affecting trading
  - **Provider Modes**: `openai_only`, `anthropic_only`, `primary_fallback`, `ensemble`
    - Ensemble mode: Both providers must agree; contradictions are dropped and recorded as disagreements
    - Primary fallback mode: Try primary provider, fallback to secondary on error
  - **Market Regime Detection**: Bull/bear trend (SPY vs MA50) × Low/medium/high volatility classification
  - **RSS Integration**: 24-hour lookback, 100 headline cap, deduplication, prioritization
  - **Safety Guardrails**:
    - Minimum confidence threshold (default: 0.70)
    - Proposal TTL (default: 120 minutes)
    - Max sector toggles per day (default: 1)
    - Cooldown period per sector (default: 3 days)
  - **Auto-Generation**: Every 4 hours (configurable), best-effort execution never blocks trading
  - **Audit Trail**: Proposals file + append-only history file + ledger events

- **API Endpoints**:
  - `GET /universe/proposals` - List current proposals and disagreements
  - `POST /universe/proposals/generate` - Generate new proposals manually
  - `POST /universe/proposals/{id}/approve` - Approve proposal and stage UniverseRegistry change
  - `POST /universe/proposals/{id}/reject` - Reject proposal

- **Dashboard UI**:
  - Advisor Suggestions section with market regime display
  - Proposal cards showing sector, action (enable/disable), confidence, rationale, supporting headlines
  - Approve/reject buttons for NEW proposals
  - Provider disagreements display (read-only)
  - Auto-refresh integration (30 seconds)

- **Configuration** (`config/config.yaml`):
  - New `llm` section with 13 configuration options
  - Environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

### Changed
- **Runner Integration**: Auto-generation at loop start, mark proposals as APPLIED after activation
- **Config Model**: Added 13 new LLM-related fields to `Config` class

### Technical
- New modules:
  - `src/app/llm/providers/` - LLM provider abstraction (base, OpenAI, Anthropic)
  - `src/app/llm/factory.py` - Provider factory with lazy imports
  - `src/app/universe_advisor/` - Regime detection, generation, guardrails, storage, apply logic
  - `tests/mocks/mock_llm_provider.py` - Mock provider for deterministic testing
- New test suites:
  - `tests/test_mock_llm_provider.py` - Mock provider tests (3 tests)
  - `tests/test_universe_advisor.py` - Comprehensive advisor tests (13 tests)
- Updated: `docs/ARCHITECTURE.md` with Universe Advisor documentation (579 lines)
- Lazy imports prevent requiring OpenAI/Anthropic packages when feature disabled

### Safety Guarantees
- Operator approval required for all changes
- Best-effort generation never blocks trading
- Next-tick activation through UniverseRegistry (deterministic timing)
- Complete audit trail via ledger and history file
- Graceful degradation (missing API keys, RSS events, regime data)

## 2025-12-22 - Startup Reconciliation

### Added
- **Startup Reconciliation**: Bot now reconciles local state with broker on every startup
  - Syncs open orders: adds broker orders to local state, removes stale local orders
  - Syncs positions: updates risk manager with broker's actual positions (quantity, avg price)
  - Provides detailed logging of all changes during reconciliation
  - Handles broker API errors gracefully

- **CLI Flag**: `--reconcile-only`
  - Performs reconciliation and prints summary, then exits without running trading loop
  - Useful for diagnostics and state verification
  - Example: `python -m src.app --mode paper --reconcile-only`

- **Broker API Extensions**:
  - `Broker.get_positions()`: Returns current positions from broker
  - Implemented for both MockBroker and AlpacaBroker
  - MockBroker now tracks positions internally for testing

### Changed
- Reconciliation runs automatically before trading loop on every startup
- State is saved immediately after reconciliation completes

### Technical
- New module: `src/app/reconciliation.py`
- New test suite: `tests/test_reconciliation.py`
- Updated: `docs/ARCHITECTURE.md` with reconciliation documentation
