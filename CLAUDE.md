# AI Trader Repo Rules

## Safety + correctness
- Default to PAPER trading mode. Never enable live trading by default.
- All orders MUST pass RiskManager checks (position sizing, max daily loss, max positions).
- Write unit tests for money-impacting logic (position sizing, risk gates).
- Never invent prices or fills; all trading decisions must log data used.

## Architecture
- Keep layers separate:
  - data/ (market data)
  - signals/ (models and signals)
  - risk/ (hard constraints)
  - broker/ (order placement)
  - app/ (runner)
- Any new feature must include logging and a minimal test if it affects orders.

## Output
- Prefer readable code, small functions, typed models (Pydantic).
- Add a structured JSON log per run plus a human-readable summary.
