

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

# Alpaca Operator Console (PowerShell)

Quick reference for the Alpaca operator console script (`tools\alpaca.ps1`).

**Prerequisites:**
- Paper requires env vars: `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY`
- Live requires env vars: `ALPACA_LIVE_KEY_ID` and `ALPACA_LIVE_SECRET_KEY`
- Live buy/sell require: `ALPACA_LIVE_ARM='YES'` and `-Confirm` parameter

**PAPER (default) sanity checks:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions
```

**PAPER place a LIMIT buy (recommended after-hours):**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Symbol SPY -Qty 1 -Type limit -Limit 400.00 -Extended
```

**PAPER cancel everything:**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 cancel-all
```

**LIVE read-only (no arming required):**
```powershell
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 status -Mode live
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 orders -Mode live
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 positions -Mode live
```

**LIVE cancel-all (arming required):**
```powershell
$env:ALPACA_LIVE_ARM="YES"
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 cancel-all -Mode live
```

**LIVE place order (arming + confirm required):**
```powershell
$env:ALPACA_LIVE_ARM="YES"
powershell -ExecutionPolicy Bypass -File tools\alpaca.ps1 buy -Mode live -Symbol SPY -Qty 1 -Type limit -Limit 400.00 -Confirm "LIVE-SPY-1-buy"
```

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

## Development Setup

* Run `pre-commit install` once to enable automatic linting/formatting on commit.
* CI enforces the same ruff checks as pre-commit.
