# AI Co-Pilot Implementation Gap Analysis

## Critical Issues

### 1. ❌ WRONG BASE BRANCH
**Required**: `milestone/api-gateway-mvp`
**Current**: Branch does not exist in repository
**Action**: Branch was created from `main` instead as `feature/ai-copilot-core-and-ui`

**Available branches**:
- main
- feature/utilization-exits-universe-fix
- feature/sell-reconcile-and-universe-rotation
- feature/strategy-dashboard
- Other feature branches

### 2. ❌ MISSING: Trading Disabled Integration (CRITICAL SAFETY)
**Required**: Global safety override via existing "Disable Trading" toggle
**Status**: NOT IMPLEMENTED

**What's needed**:
- Read `state/pause_trading.flag` (found at src/ui_api/app.py:1858)
- If trading disabled → force `ai_copilot.enabled_effective = false`
- Skip all AI calls when trading disabled
- Prevent AI file writes (journal/memory)
- Status must show `forced_reason="forced_off_by_trading_disable"`
- UI banner: "🛑 Trading is disabled. AI Co-Pilot is paused."

**Impact**: This is the PRIMARY SAFETY MECHANISM - without it, AI Co-Pilot could run when trading is paused.

### 3. ❌ MISSING: UI Runtime Overrides File
**Required**: `data/ui_runtime_overrides.json`
**Status**: NOT IMPLEMENTED

**What's needed**:
- Load safely (invalid JSON → ignore + log warning)
- Atomic writes (temp file → rename)
- Only allow safe fields:
  - ai_copilot.enabled
  - feature enables (trade_rationale, daily_journal, strategy_critique)
  - max_calls_per_run
  - dry_run
  - budgets.global_max_output_tokens
- MUST NOT allow:
  - influence_decisions
  - trading logic changes

**Current**: UI routes exist but write nothing to disk

### 4. ❌ MISSING: Effective Config with Sources
**Required**: Helper that returns effective value + source per field
**Status**: NOT IMPLEMENTED

**What's needed**:
```python
{
  "effective": {"enabled": false, ...},
  "sources": {"enabled": "trading_disabled", ...}
}
```

**Sources**: "trading_disabled" > "env" > "ui" > "yaml" > "default"

**Current**: No source tracking

### 5. ⚠️ WRONG CONFIG STRUCTURE
**Required**:
```yaml
ai_copilot:
  budgets:
    global_max_output_tokens: 1200
  trade_rationale:
    enabled: true
    max_output_tokens: 500
  daily_journal:
    enabled: true
    max_output_tokens: 1200
  strategy_critique:
    enabled: true
    max_output_tokens: 900
```

**Current**:
```yaml
ai_copilot:
  max_output_tokens: 350  # flat, not per-feature
  trade_rationale:
    enabled: true  # no max_output_tokens
```

**Issue**: Missing nested budget structure and per-feature token limits

### 6. ⚠️ WRONG OUTPUT SCHEMAS
**Trade Rationale - Required**:
```json
{
  "thesis": "string (1 sentence)",
  "counterarguments": ["string","string"],
  "invalidation_conditions": ["string","string","string"]
}
```

**Trade Rationale - Current**:
```json
{
  "rationale": "2-3 sentences",
  "confidence": 85,
  "risk_factors": ["string","string"]
}
```

**Strategy Critique - Required**:
```json
{
  "date": "YYYY-MM-DD",
  "what_worked": ["..."],
  "what_failed": ["..."],
  "suggested_tweaks": ["..."],
  "confidence": 0.0-1.0
}
```

**Strategy Critique - Current**:
```json
{
  "critique": "...",
  "recommendations": ["..."],
  "confidence": 75,
  "strengths": ["..."],
  "weaknesses": ["..."]
}
```

### 7. ⚠️ MISSING: Token Budget Enforcement
**Required**: `effective_max_output_tokens = min(feature.max_output_tokens, budgets.global_max_output_tokens)`

**Current**: Only enforces global `max_output_tokens: 350`

### 8. ❌ MISSING: Status Snapshot Structure
**Required**:
```json
{
  "trading_disabled_effective": true/false,
  "ai_copilot_enabled_effective": true/false,
  "forced_reason": "... or null",
  "artifacts": {
    "latest_journal_path": "... or null",
    "latest_critique_path": "... or null"
  }
}
```

**Current**: Different structure, missing trading_disabled tracking

### 9. ❌ MISSING: API Endpoints
**Required**:
- GET `/api/ai-copilot/config` (returns effective + sources)
- POST `/api/ai-copilot/config` (with validate_only support)
- GET `/api/ai-copilot/status`
- GET `/api/ai-copilot/critique?limit=5`

**Current**:
- GET `/ai-copilot/status` (different structure)
- GET `/ai-copilot/features`
- GET `/ai-copilot/critiques?n=7`
- POST `/ai-copilot/toggle`
- POST `/ai-copilot/features/{feature}`

**Issue**: Different paths, missing config endpoint, missing validate_only

### 10. ❌ MISSING: Smoketest Tool
**Required**: `python -m tools.ai_copilot_smoketest`

**Status**: NOT IMPLEMENTED

**Must print**:
- trading_disabled_effective
- ai_copilot effective enabled + sources
- max_calls_per_run and global_max_output_tokens
- override file exists/writable
- where latest_status.json writes

### 11. ❌ MISSING: CLI Journal Tool
**Required**: `python -m tools.generate_daily_journal --date YYYY-MM-DD`

**Status**: NOT IMPLEMENTED

### 12. ❌ MISSING: UI Page
**Required**: Full "AI Co-Pilot" tab/page with:
- Effective values + sources display
- Safe controls only
- Trading disabled banner
- Latest status info
- Last 5 critiques

**Current**: Routes exist but no HTML/frontend

### 13. ⚠️ MISSING: Dry-Run Enforcement
**Required**: `dry_run` prevents file writes

**Current**: `AI_COPILOT_DRY_RUN=1` supported but not checked in journal/critique writers for file prevention

### 14. ⚠️ MISSING: Enhanced Client Features
**Required**:
- Strict JSON schema validation
- Token budget enforcement (min of feature and global)

**Current**:
- Basic schema validation via LLM provider
- Only global token limit

---

## What WAS Implemented Correctly ✅

1. ✅ Core CoPilotClient with budget gates
2. ✅ Graceful degradation (never throws)
3. ✅ Exponential backoff retries
4. ✅ Timeout enforcement
5. ✅ Trade rationale advisor (wrong schema but structure correct)
6. ✅ Daily journal generator (needs dry-run check)
7. ✅ Strategy critique (wrong schema but structure correct)
8. ✅ Status snapshot writer (wrong structure)
9. ✅ Basic UI routes (wrong paths)
10. ✅ 19 unit tests (all passing)
11. ✅ Comprehensive documentation (AI_COPILOT.md)
12. ✅ Config loading in config.py (needs extension)
13. ✅ Environment variable override for AI_COPILOT_ENABLED

---

## Priority Order for Fixes

### P0 - CRITICAL (Required for safety)
1. **Trading disabled integration** - Global safety override
2. **UI runtime overrides file** - Core functionality
3. **Effective config with sources** - Required transparency

### P1 - HIGH (Required for spec compliance)
4. **Correct config structure** - Nested budgets + per-feature tokens
5. **Correct output schemas** - Trade rationale + critique
6. **Token budget enforcement** - min(feature, global)
7. **Smoketest tool** - Required verification
8. **API endpoint corrections** - /api/ai-copilot/config

### P2 - MEDIUM (Important but can be quick)
9. **Dry-run enforcement** - Prevent file writes properly
10. **CLI journal tool** - `python -m tools.generate_daily_journal`
11. **Status snapshot structure** - Match required format
12. **Enhanced validation** - Strict JSON schema

### P3 - LOW (Can defer if time-constrained)
13. **UI page** - HTML/frontend (routes exist, UI can be added later)
14. **Additional API endpoints** - GET /api/ai-copilot/critique

---

## Estimated Work Required

**Critical Safety (P0)**: ~2-3 hours
- Trading disabled integration: 1 hour
- UI runtime overrides: 1 hour
- Effective config with sources: 30 min

**Spec Compliance (P1)**: ~3-4 hours
- Config structure update: 30 min
- Schema updates: 1 hour
- Token budget enforcement: 30 min
- Smoketest tool: 30 min
- API endpoints: 1 hour
- Update tests: 1 hour

**Polish (P2+P3)**: ~2-3 hours
- Dry-run enforcement: 30 min
- CLI tool: 30 min
- Status structure: 30 min
- UI page: 1-2 hours
- Documentation updates: 30 min

**Total**: ~7-10 hours for full compliance

---

## Recommendation

**Option A: Complete Implementation on Current Branch**
- Continue on `feature/ai-copilot-core-and-ui` (already has commit)
- Add all missing P0-P2 features
- Defer P3 UI page if time-constrained
- Can still be "working by tomorrow"

**Option B: Start Fresh on Correct Branch**
- Create `feature/ai-copilot-ui-safe-controls` from `main` (since milestone/api-gateway-mvp doesn't exist)
- Port over working code
- Add all missing features
- More commits but cleaner history

**Option C: Ask User**
- Clarify if milestone/api-gateway-mvp should be created or if main is acceptable
- Confirm priority: safety features vs spec compliance vs UI
- Get guidance on time budget

**My Recommendation**: Option A (complete on current branch) for fastest delivery, then can create clean branch later if needed for PR.

---

## Summary

**Current State**: ~60% complete
- ✅ Core architecture and safety mechanisms
- ✅ Basic features implemented
- ❌ Missing critical trading disabled integration
- ❌ Missing UI runtime overrides
- ⚠️ Wrong schemas and config structure
- ❌ Missing verification tools

**To be "working by tomorrow"**: Focus on P0 (safety) + P1 (compliance), defer P3 (UI page HTML).
