# Pending Changes Review

## Overview
7 modified files with changes across configuration, allocator, and universe advisor modules.

---

## Configuration Changes (3 files)

### 1. config/config.yaml
**Type**: Parameter tuning for more active trading

**Changes**:
- **Risk limits** (lines 9-11):
  - `max_order_usd`: $100 → $2,500 (25x increase)
  - `max_gross_exposure_usd`: $10,000 → $50,000 (5x increase)
  - `max_daily_loss_usd`: $250 (unchanged)

- **LLM guardrails** (line 73):
  - `min_confidence`: 0.70 → 0.60 (more permissive)

- **Constituent proposals** (lines 89-93):
  - `max_add_per_run`: 2 → 3 (more candidates per run)
  - `min_confidence_add`: 0.80 → 0.70 (more permissive)
  - `cooldown_days_per_ticker`: 7 → 5 (faster re-evaluation)

**Assessment**: These are parameter adjustments to increase trading activity. Should be committed as a separate "config: tune parameters for more active trading" commit.

---

### 2. config/selector.yaml
**Type**: Parameter tuning

**Changes**:
- `candidates_min_confidence`: 0.70 → 0.60 (line 194)

**Assessment**: Consistent with config.yaml changes. Should be in same commit.

---

### 3. config/strategies.yaml
**Type**: Strategy configuration tuning

**Changes**:
- **Per-strategy limits** (multiple strategies):
  - `max_position_size`: Increased (e.g., $5k → $8k)
  - `max_positions`: Increased (e.g., 3 → 10)

- **Strategy enablement** (line 37):
  - `Momentum_MACD` enabled (was disabled)

- **Global limits** (line 50):
  - `max_total_positions`: 10 → 20

**Assessment**: Part of the same parameter tuning initiative. Should be in same commit as other config files.

---

## Source Code Changes (4 files)

### 4. src/app/allocator.py
**Type**: Bug fix for dry-run mode support

**Changes** (lines 117-124, 173, 185, 198):
- Added MockBroker detection for dry-run mode
- Uses mock equity ($100k) when broker doesn't have `client` attribute
- Added Decimal → float conversions for JSON serialization in ledger events

**Code**:
```python
if hasattr(self.broker, 'client'):
    account_state = self.broker.client.get_account()
    account_dict = {"equity": str(account_state.equity)}
    equity = allocation.get_total_equity(account_dict)
else:
    # MockBroker in dry-run mode - use mock equity
    self.logger.info("MockBroker detected - using mock equity for allocation")
    equity = Decimal("100000.00")  # Mock $100k equity for dry-run
```

**Assessment**: This is a bug fix that enables allocation to work in dry-run mode. Should be a separate commit: "fix(allocator): support MockBroker in dry-run mode"

---

### 5. src/app/universe_advisor/guardrails.py
**Type**: Feature enhancement - filter reason tracking

**Changes**:
- Changed return type: `ProposalSet` → `tuple[ProposalSet, dict[str, list[str]]]`
- Returns filter reasons along with filtered proposals
- Enhanced filter messages with details:
  - Shows exact confidence values
  - Shows days remaining in cooldown periods
  - Clearer expiry messages

**Example**:
```python
reason = f"{cooldown_days}-day cooldown active (last toggle {days_ago}d ago, {days_remaining}d remaining)"
```

**Assessment**: Feature enhancement to provide transparency on filtering decisions. Should be separate commit: "feat(advisor): track and return filter reasons from guardrails"

**Note**: This changes the function signature, so callers must be updated.

---

### 6. src/app/universe_advisor/storage.py
**Type**: Feature support - store filter reasons

**Changes**:
- Added optional `filter_reasons` parameter to `save_proposals()`
- Saves filter reasons to proposals JSON file
- Whitespace cleanup (trailing spaces)

**Code**:
```python
def save_proposals(
    proposal_set: ProposalSet,
    file_path: Path,
    filter_reasons: dict[str, list[str]] | None = None
) -> None:
```

**Assessment**: Companion change to guardrails.py. Should be in same commit as guardrails changes.

---

### 7. src/app/universe_registry.py
**Type**: Bug fix - update enabled state

**Changes** (line 169):
- Added `override.enabled = enabled` when staging sector toggle

**Code**:
```python
if sector_name in self.overrides:
    override = self.overrides[sector_name]
    override.enabled = enabled  # Update enabled state
    override.pending_version = (override.active_version or 0) + 1
```

**Assessment**: Bug fix to ensure enabled state is properly updated. Should be separate commit: "fix(registry): update enabled state when staging sector toggle"

---

## Recommended Commit Strategy

### Commit 1: Configuration Tuning
**Files**:
- config/config.yaml
- config/selector.yaml
- config/strategies.yaml

**Message**:
```
config: tune parameters for more active trading

Adjusted risk limits and strategy parameters to enable more active
trading with higher position sizes and more concurrent positions:

Risk limits:
- max_order_usd: $100 → $2,500
- max_gross_exposure_usd: $10k → $50k

Strategy limits:
- Increased max_position_size across all strategies
- Increased max_positions per strategy (3-5 → 10)
- Increased max_total_positions: 10 → 20
- Enabled Momentum_MACD strategy

Confidence thresholds:
- Lowered min_confidence: 0.70 → 0.60 (more permissive)
- Lowered candidates_min_confidence: 0.70 → 0.60
- Lowered min_confidence_add: 0.80 → 0.70

Constituent proposals:
- Increased max_add_per_run: 2 → 3
- Reduced cooldown_days_per_ticker: 7 → 5

These changes allow the system to take larger positions, manage more
concurrent trades, and generate more proposals while maintaining safety
through unchanged daily loss limits.
```

---

### Commit 2: Allocator Dry-Run Support
**Files**:
- src/app/allocator.py

**Message**:
```
fix(allocator): support MockBroker in dry-run mode

Added MockBroker detection to handle dry-run mode where broker doesn't
have a real Alpaca client:

- Check for broker.client attribute before accessing
- Use mock equity ($100k) when MockBroker is detected
- Convert Decimal to float for JSON serialization in ledger events

This enables allocation to work correctly in dry-run/testing scenarios
without requiring actual broker API access.

Fixes: TypeError when accessing broker.client on MockBroker
```

---

### Commit 3: Filter Reasons Tracking
**Files**:
- src/app/universe_advisor/guardrails.py
- src/app/universe_advisor/storage.py

**Message**:
```
feat(advisor): track and return filter reasons from guardrails

Enhanced guardrails to provide transparency on why proposals were
filtered:

Changes:
- apply_guardrails() now returns tuple: (ProposalSet, filter_reasons)
- filter_reasons maps sector_name → list of human-readable reasons
- Enhanced filter messages with specific details:
  - Confidence: shows actual vs required values
  - Cooldown: shows days elapsed and days remaining
  - Max toggles: shows limit that was exceeded

- save_proposals() now accepts optional filter_reasons parameter
- Saves filter reasons to proposals JSON for dashboard display

This provides operators with clear visibility into why certain
proposals were not generated or were filtered out.
```

---

### Commit 4: Registry Enabled State Fix
**Files**:
- src/app/universe_registry.py

**Message**:
```
fix(registry): update enabled state when staging sector toggle

Added missing line to update override.enabled when staging a sector
toggle change. Without this, the enabled state could become stale when
repeatedly toggling a sector.

Fix: override.enabled = enabled (line 169)

This ensures the staged pending version has the correct enabled state
that will be activated on the next loop tick.
```

---

## Verification Checklist

Before committing:

### Commit 1 (Config):
- [ ] Verify all config files parse correctly
- [ ] Check if ARCHITECTURE.md needs updates for new limits
- [ ] Test that strategies load with new parameters

### Commit 2 (Allocator):
- [ ] Test dry-run mode works with MockBroker
- [ ] Verify allocation still works with real broker
- [ ] Check ledger events serialize correctly

### Commit 3 (Filter Reasons):
- [ ] Verify all callers of apply_guardrails() updated to handle tuple return
- [ ] Test that filter_reasons appear in proposals JSON
- [ ] Check dashboard displays filter reasons correctly

### Commit 4 (Registry):
- [ ] Test sector toggle preserves enabled state
- [ ] Verify pending version activation applies correct enabled value
- [ ] Check that repeated toggles work correctly

---

## Dependencies & Order

**Recommended commit order**:
1. Commit 4 (Registry fix) - Independent bug fix
2. Commit 2 (Allocator fix) - Independent bug fix
3. Commit 3 (Filter reasons) - Feature enhancement
4. Commit 1 (Config tuning) - Parameter changes

Or commit all 4 independently in any order since they're mostly independent.

---

## Notes

- Config changes are intentional parameter tuning for more active trading
- Allocator and registry changes are bug fixes
- Guardrails/storage changes are a feature enhancement
- All changes appear reasonable and well-scoped
- No obvious breaking changes or risks identified
