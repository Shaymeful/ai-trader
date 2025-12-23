

# Repo Rules (must follow)
===

# 

# \## Documentation rule (MANDATORY)

# Any change that adds/changes behavior, CLI flags, providers/brokers, safety gates, env vars, outputs/logging, or tests

# MUST update:

# \- docs/ARCHITECTURE.md (authoritative feature/architecture log)

# 

# If the change is user-visible, also update:

# \- docs/CHANGELOG.md (optional but recommended)

# 

# Pull requests/commits are not complete until docs are updated.

# 

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
