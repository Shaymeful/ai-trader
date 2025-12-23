

# Repo Rules (must follow)

## Spec Sync Rule (MANDATORY)

**Any change to these areas MUST update docs/ARCHITECTURE.md in the SAME commit:**

- [ ] Runtime behavior or trading logic
- [ ] CLI flags or arguments
- [ ] Configuration (env vars, config file structure)
- [ ] Broker or data provider interfaces
- [ ] Risk controls or safety gates
- [ ] Order execution logic or pipeline
- [ ] Output formats or logging

**Checklist before committing:**
1. Did I change behavior, flags, config, interfaces, or risk controls?
2. If yes, did I update docs/ARCHITECTURE.md to reflect the change?
3. Did I verify the change is documented in the relevant section?

**If the change is user-visible, also update:**
- docs/CHANGELOG.md (optional but recommended)

**Rule:** Pull requests/commits touching the above areas are incomplete without docs updates.

---

# AI Trader Repo Rules

## Safety + correctness

* Default to PAPER trading mode. Never enable live trading by default.
* All orders MUST pass RiskManager checks (position sizing, max daily loss, max positions).
* Write unit tests for money-impacting logic (position sizing, risk gates).
* Never invent prices or fills; all trading decisions must log data used.

## Architecture

* Keep layers separate:

  * data/ (market data)
  * signals/ (models and signals)
  * risk/ (hard constraints)
  * broker/ (order placement)
  * app/ (runner)

* Any new feature must include logging and a minimal test if it affects orders.

## Output

* Prefer readable code, small functions, typed models (Pydantic).
* Add a structured JSON log per run plus a human-readable summary.
