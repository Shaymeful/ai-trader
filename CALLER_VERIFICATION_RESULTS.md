# Apply Guardrails Caller Verification Results

## Issue Identified

After committing the filter reasons feature (commit `9af9c7d`), the `apply_guardrails()` function signature changed from:

```python
def apply_guardrails(...) -> ProposalSet:
```

to:

```python
def apply_guardrails(...) -> tuple[ProposalSet, dict[str, list[str]]]:
```

This was a **breaking change** that required all callers to be updated to handle the tuple return value.

---

## Search Results

Found **6 files** mentioning `apply_guardrails`:

| File | Type | Status |
|------|------|--------|
| `PENDING_CHANGES_REVIEW.md` | Documentation | N/A |
| `docs/ARCHITECTURE.md` | Documentation | N/A |
| `src/app/universe_advisor/guardrails.py` | Implementation | N/A |
| `src/ui_api/app.py` | Caller | ✅ Already updated |
| `src/app/runner.py` | Caller | ❌ Not updated |
| `tests/test_universe_advisor.py` | Test callers (4) | ❌ Not updated |

---

## Callers Found

### ✅ Already Updated

**File**: `src/ui_api/app.py:1479`

```python
proposal_set, filter_reasons = apply_guardrails(
    proposal_set, guardrails_config, history_file
)
```

**Status**: Correctly handles tuple return and passes `filter_reasons` to downstream functions.

---

### ❌ Not Updated (Fixed)

#### 1. src/app/runner.py:1343

**Before**:
```python
proposal_set = apply_guardrails(
    proposal_set, guardrails_config, history_file
)

# Save
save_proposals(proposal_set, proposals_file)
```

**After**:
```python
proposal_set, filter_reasons = apply_guardrails(
    proposal_set, guardrails_config, history_file
)

# Save
save_proposals(proposal_set, proposals_file, filter_reasons)
```

**Impact**:
- Runner auto-generation would fail with `ValueError: too many values to unpack`
- Filter reasons would not be persisted to proposals JSON

---

#### 2. tests/test_universe_advisor.py (4 occurrences)

**Test functions updated**:
- `test_apply_guardrails_confidence_filter` (line 335)
- `test_apply_guardrails_cooldown` (line 384)
- `test_apply_guardrails_ttl_expired` (line 499)
- `test_apply_guardrails_max_toggles_per_day` (line 548)

**Before**:
```python
filtered_set = apply_guardrails(proposal_set, guardrails_config, history_file)
```

**After**:
```python
filtered_set, _ = apply_guardrails(proposal_set, guardrails_config, history_file)
```

**Note**: Tests don't need `filter_reasons`, so using `_` to ignore the second tuple element.

**Impact**: All 4 tests would fail with `ValueError: too many values to unpack`

---

## Fixes Applied

### Commit: `fffc351`

**Title**: `fix(advisor): update callers to handle guardrails tuple return`

**Files Changed**:
- `src/app/runner.py`: Updated auto-generation to unpack tuple and pass filter_reasons
- `tests/test_universe_advisor.py`: Updated 4 test functions to unpack tuple

**Verification**:
- ✅ All 17 tests in `test_universe_advisor.py` pass
- ✅ Linting passes for both files
- ✅ Runner will now persist filter reasons to proposals JSON

---

## Summary

| Metric | Count |
|--------|-------|
| Total callers found | 6 |
| Already updated | 1 |
| Needed updating | 5 |
| Fixed in commit fffc351 | 5 |
| Tests passing | 17/17 ✅ |

---

## Lesson Learned

**Breaking Changes Checklist**:

When changing a function signature (especially return types):

1. ✅ Update the function implementation
2. ✅ Update all callers in source code
3. ✅ Update all callers in tests
4. ✅ Run full test suite to verify
5. ✅ Document the breaking change in commit message
6. ✅ Consider deprecation period for public APIs

In this case, step 2 and 3 were initially missed for some callers, requiring a follow-up fix commit.

---

## Related Commits

- `9af9c7d`: feat(advisor): track and return filter reasons from guardrails (introduced breaking change)
- `fffc351`: fix(advisor): update callers to handle guardrails tuple return (fixed all callers)
