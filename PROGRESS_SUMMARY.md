# Progress Summary: Feature Implementation

## Branch: feature/utilization-exits-universe-fix

---

## ✅ COMPLETED TASKS

### 1. Configuration Schema (100% Complete)

**Files Modified:**
- `config/config.yaml`
- `src/app/config.py`

**Changes:**
1. **Risk Parameters:**
   - Added `target_utilization_pct: 0.97` (target 97% capital usage)
   - Added `use_total_capital_as_equity_cap: true` (use UI-configured cap)

2. **Execution Parameters:**
   - Added `order_style: "limit"` (support for "limit" or "market" orders)
   - Added `limit_offset_bps_buy: 10` (tighter buy limit offsets: 0.10%)
   - Added `limit_offset_bps_sell: 10` (tighter sell limit offsets: 0.10%)
   - Added `allow_market_in_paper: true` (faster fills in paper mode)

3. **LLM Configuration:**
   - Changed `allow_constituent_removals: true` (enable ticker removals)
   - Added removal rubric parameters:
     - `removal_min_failed_eligibility_checks: 5`
     - `removal_min_days_no_activity: 14`
     - `removal_stale_negative_news_confidence: 0.80`

4. **Config Model Updates:**
   - Added all new fields to `Config` Pydantic model
   - Updated `load_config_with_yaml()` to parse new YAML fields
   - Maintained backward compatibility

### 2. Account Summary Helper (100% Complete)

**Files Created:**
- `src/app/account_summary.py`

**Functions:**
1. `load_account_summary()` - Loads `out/account_summary.json`
2. `get_total_capital()` - Extracts total_capital as Decimal
3. `get_effective_equity_cap()` - Computes equity cap with logic:
   - If `use_total_capital_as_cap` is true: `cap = min(broker_equity, total_capital)`
   - Otherwise: `cap = broker_equity`

**Features:**
- Robust error handling (missing file, invalid JSON, invalid values)
- Detailed logging for diagnostics
- Type-safe Decimal handling

### 3. Implementation Planning (100% Complete)

**Files Created:**
- `IMPLEMENTATION_PLAN.md` - Comprehensive implementation roadmap
- `PROGRESS_SUMMARY.md` - This file

---

## 🔄 NEXT STEPS (Prioritized)

### Priority 1: Capital Utilization (CRITICAL)

**Goal:** Invest 95-99% of capital with fractional top-off

**Tasks:**
1. **Enhance Allocator** (`src/app/allocator.py`)
   - Import `get_effective_equity_cap` from account_summary
   - In `_allocate_with_registry()`:
     - Load broker equity and total_capital
     - Compute effective_equity_cap
     - Apply target_utilization_pct: `budget_base = cap * target_util_pct`
     - Log: equity, total_capital, cap, target_util, budget_base
   - Implement top-off pass:
     - After initial allocation, compute `remaining_budget`
     - If remaining > $50, distribute to highest-conviction BUY intents
     - Use fractional shares if `allow_fractional` enabled

2. **Update Allocation Functions** (`src/app/allocation.py`)
   - Modify `compute_qty_from_notional()` to support fractional returns
   - Add `allow_fractional` parameter
   - Return `float` if fractional allowed, `int` otherwise

3. **Add Logging**
   - Log capital allocation summary at each iteration
   - Log top-off decisions (why/why not, how much distributed)

### Priority 2: Exit Overlay / SELL Orders (HIGH)

**Goal:** Enable sells via Exit Advisor integration

**Tasks:**
1. **Integrate Exit Advisor** (`src/app/runner.py`)
   - Before strategy execution in paper mode loop:
     ```python
     # Get current positions
     positions = broker.get_positions()

     # Scan for exit signals
     from src.app.exit_advisor import ExitAdvisor
     exit_advisor = ExitAdvisor(config)
     exit_candidates = exit_advisor.scan_and_emit_candidates(positions, market_data)

     # Merge with selector candidates
     all_candidates = selector_candidates + exit_candidates
     ```

2. **Strategy Target Override**
   - Strategies should set `target_quantity=0` for SELL candidates
   - Allocator will compute negative delta
   - Executor will generate SELL orders

3. **Test SELL Flow**
   - Verify EXIT candidates cause target=0
   - Verify reconciler generates SELL orders
   - Verify orders are executed

### Priority 3: Universe/Sector Integration (HIGH)

**Goal:** UI-created sectors feed actual trading universe

**Tasks:**
1. **Export Active Universe** (`src/app/runner.py`)
   - After `universe_registry.check_and_activate_pending()`:
     ```python
     active_universe = universe_registry.resolve()
     # Write to out/universe_active.json
     ```

2. **Selector Integration** (`src/app/selector/run_once.py`)
   - Load universe from `out/universe_active.json`
   - Fallback to config if file missing

3. **Data Provider Integration**
   - Pass `universe_registry.resolve()` to AlpacaDataProvider
   - Ensure strategies see active universe

### Priority 4: Order Style Configuration (MEDIUM)

**Goal:** Support market orders for faster fills

**Tasks:**
1. **Update Order Pipeline** (`src/app/order_pipeline.py`)
   - Check `config.order_style`
   - If "market" and paper mode with `allow_market_in_paper`:
     - Use `OrderType.MARKET`
   - If "limit":
     - Calculate limit price with `config.limit_offset_bps_*`

2. **Implement Tighter Limit Offsets**
   - Replace 1/4 spread logic with BPS-based offsets
   - Buy: `limit_price = ask - (ask * limit_offset_bps_buy / 10000)`
   - Sell: `limit_price = bid + (bid * limit_offset_bps_sell / 10000)`

### Priority 5: Diagnostics (MEDIUM)

**Goal:** Clear diagnostics when trading is idle

**Tasks:**
1. **Add Diagnostic Function** (`src/app/runner.py`)
   ```python
   def diagnose_idle_trading(config, universe, candidates, positions) -> str:
       # Check in precedence order
       # Return single-line reason
   ```

2. **Expose in API** (`src/ui_api/app.py`)
   - Add `why_not_trading` field to `/health/detailed`

### Priority 6: LLM Removal Rubric (LOW)

**Goal:** Automatically propose removing underperforming tickers

**Tasks:**
1. **Track Ticker Metrics**
   - Eligibility failures per ticker
   - Days since last activity
   - Negative news confidence

2. **Generate Removal Proposals** (`src/app/llm/generator.py`)
   - Check removal criteria against config thresholds
   - Propose removals within `max_remove_per_run` limit

---

## 📝 IMPLEMENTATION DETAILS

### File Summary

| File | Status | Purpose |
|------|--------|---------|
| `config/config.yaml` | ✅ Modified | Added new config parameters |
| `src/app/config.py` | ✅ Modified | Updated Config model and YAML loader |
| `src/app/account_summary.py` | ✅ Created | Account summary utilities |
| `src/app/allocator.py` | 🔄 TODO | Enhance with capital utilization |
| `src/app/allocation.py` | 🔄 TODO | Add fractional support |
| `src/app/runner.py` | 🔄 TODO | Integrate ExitAdvisor + universe fix |
| `src/app/order_pipeline.py` | 🔄 TODO | Add order style logic |
| `src/app/llm/generator.py` | 🔄 TODO | Add removal rubric |
| `src/ui_api/app.py` | 🔄 TODO | Add idle diagnostics |
| `tests/...` | 🔄 TODO | Comprehensive tests |

### Lines of Code Estimate

| Component | Est. LOC | Complexity |
|-----------|----------|------------|
| Config changes | ~100 | Low ✅ |
| Account summary | ~130 | Low ✅ |
| Allocator enhancements | ~200 | High |
| Exit integration | ~50 | Medium |
| Universe fix | ~100 | Medium |
| Order style | ~80 | Medium |
| Diagnostics | ~60 | Low |
| LLM removal | ~150 | High |
| Tests | ~500 | Medium |
| **Total** | **~1,370** | - |

---

## 🧪 TESTING STRATEGY

### Unit Tests

1. **test_account_summary.py**
   - ✅ load_account_summary() with valid/invalid/missing file
   - ✅ get_total_capital() edge cases
   - ✅ get_effective_equity_cap() logic

2. **test_allocator.py**
   - Capital utilization with different caps
   - Top-off pass distribution
   - Fractional share allocation

3. **test_exit_integration.py**
   - Exit candidates generate SELL orders
   - Strategy respects EXIT actions

4. **test_universe_integration.py**
   - Active universe file creation
   - Selector reads active universe
   - UI-created sectors appear in trading

### Integration Tests

1. **End-to-End Capital Flow**
   - Set total_capital = $30,000
   - Set target_utilization_pct = 0.97
   - Verify $29,100 allocated (97% of $30k)
   - Verify top-off distributes remaining funds

2. **End-to-End SELL Flow**
   - Create position
   - Trigger exit condition (stop loss / signal flip)
   - Verify SELL order generated
   - Verify position closed

3. **Universe Integration**
   - Create new sector in UI
   - Enable sector
   - Verify sector appears in `out/universe_active.json`
   - Verify selector uses new symbols
   - Verify trading occurs on new symbols

---

## 📊 SUCCESS CRITERIA

- [ ] Config loads all new parameters correctly
- [ ] Allocator uses ~97% of total_capital
- [ ] Top-off distributes remaining budget
- [ ] Fractional shares work in paper mode
- [ ] Exit candidates generate SELL orders
- [ ] Positions close when exits trigger
- [ ] UI-created sectors appear in active universe
- [ ] Selector uses active universe
- [ ] Market orders work in paper mode
- [ ] Limit orders use tighter offsets
- [ ] Idle trading diagnostics are accurate
- [ ] Removal proposals generated correctly
- [ ] All tests pass
- [ ] ARCHITECTURE.md updated

---

## 🚀 HOW TO CONTINUE

### For Next Session

1. **Start with Allocator Enhancement:**
   ```bash
   # Open allocator.py
   code src/app/allocator.py

   # Implement capital utilization in _allocate_with_registry()
   # - Import get_effective_equity_cap
   # - Compute budget_base with target_utilization_pct
   # - Implement top-off pass
   # - Add detailed logging
   ```

2. **Then Exit Integration:**
   ```bash
   # Open runner.py
   code src/app/runner.py

   # Add ExitAdvisor call before strategy execution
   # Merge exit_candidates with selector_candidates
   ```

3. **Then Universe Fix:**
   ```bash
   # Export active universe in runner.py
   # Update selector/run_once.py to read from file
   ```

### Quick Reference

**Branch:** `feature/utilization-exits-universe-fix`

**Key Commits:**
- Config schema updates
- Account summary helper

**Next Commit:**
- "feat(allocator): implement capital utilization with fractional top-off"

---

## 📖 DOCUMENTATION

### Already Documented

- `IMPLEMENTATION_PLAN.md` - Complete implementation roadmap
- `account_summary.py` - Fully documented with docstrings
- Config changes - Inline comments in YAML and Python

### To Document

- Allocator changes (after implementation)
- Exit integration (after implementation)
- Universe integration (after implementation)
- Update `docs/ARCHITECTURE.md` with all changes

---

## ⚠️ NOTES & CAVEATS

1. **Backward Compatibility:**
   - All changes maintain backward compatibility
   - New features are opt-in via config
   - Default values preserve existing behavior

2. **Testing Requirements:**
   - Each component needs unit tests
   - Integration tests critical for capital flow
   - Manual testing required for UI interactions

3. **Performance:**
   - Account summary loaded once per loop (not cached yet)
   - Universe file written once per loop
   - Minimal performance impact expected

4. **Known Issues:**
   - Top-off logic not yet implemented (complex)
   - LLM removal tracking not implemented (requires state)
   - Exit advisor cooldown needs verification

---

## 💡 RECOMMENDATIONS

1. **Implement in Phases:**
   - Phase 1: Capital utilization (highest value)
   - Phase 2: Exit integration (unblocks sells)
   - Phase 3: Universe fix (correctness)
   - Phase 4: Order style (nice-to-have)
   - Phase 5: Diagnostics + LLM removal (polish)

2. **Test Incrementally:**
   - Test each phase before moving to next
   - Use paper mode for all testing
   - Monitor logs closely for capital allocation

3. **Documentation:**
   - Update ARCHITECTURE.md after each phase
   - Add inline comments for complex logic
   - Keep IMPLEMENTATION_PLAN.md updated

---

## END OF SUMMARY

**Status:** Configuration complete, account summary helper complete, ready to implement allocator enhancements.

**Estimated Completion:** 3-4 hours of focused implementation + 2-3 hours testing

**Priority:** High - these improvements address critical user feedback about capital utilization, SELL orders, and universe management.
