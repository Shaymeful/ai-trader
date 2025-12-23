# Changelog

All notable changes to AI-Trader will be documented in this file.

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
