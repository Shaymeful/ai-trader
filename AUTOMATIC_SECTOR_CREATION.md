# Automatic Sector Creation - Now Fully Functional

## Overview

The "propose add" feature now works **completely automatically** from dashboard to trading. No manual config edits needed!

---

## How It Works Now (Automatic)

### 1. **Create Sector via Dashboard**
- Navigate to Candidates section
- Click "Propose Add" on any candidate
- Check "Create new sector"
- Enter sector name (e.g., "energy", "robotics", "healthcare")
- Enter description
- Click "Create Proposal"

### 2. **What Happens Automatically**

#### A. Sector Creation (Immediate)
```
POST /universe/sectors
→ Creates SectorConfig in universe_overrides.json
→ Sector is enabled=false, active_version=0
→ No manual file edits required!
```

#### B. Proposal Creation (Immediate)
```
POST /universe/proposals/constituents
→ Creates proposal to add symbol to new sector
→ Proposal status="NEW"
→ Awaiting your approval in UI
```

#### C. Approval (Manual)
```
Click "Approve" on proposal in dashboard
→ Proposal status="APPROVED"
→ Change is staged with pending_version=1
→ Saved to universe_overrides.json
```

#### D. Activation (Automatic - Next Loop)
```
Loop iteration starts
→ check_and_activate_pending() runs
→ pending_version promoted to active_version
→ Sector enabled state synced to config
→ Symbols added to trading universe
```

#### E. Trading (Automatic)
```
Universe resolution runs
→ Includes all enabled sectors (base + UI-created)
→ Generates candidates for new symbols
→ Places live orders
```

---

## Technical Implementation

### Fix #1: Load Override-Only Sectors

**File**: `src/app/universe_registry.py`

**Before** (Broken):
```python
def _apply_overrides(self, overrides_data: dict):
    for sector_name, override_data in sector_overrides.items():
        if sector_name not in self.sectors:
            logger.warning(f"Override for unknown sector '{sector_name}' (ignoring)")
            continue  # ❌ Skipped UI-created sectors
```

**After** (Fixed):
```python
def _apply_overrides(self, overrides_data: dict):
    for sector_name, override_data in sector_overrides.items():
        if sector_name not in self.sectors:
            # ✅ Create sector from override
            self.sectors[sector_name] = SectorConfig(
                name=sector_name,
                description=f"User-created sector: {sector_name}",
                symbols=override.tickers or [],
                enabled=override.enabled,
            )
```

**Result**: UI-created sectors now load automatically without `config.yaml` entry

---

### Fix #2: Sync State During Activation

**File**: `src/app/universe_registry.py`

**Before** (Broken):
```python
def check_and_activate_pending(self):
    for sector_name, override in self.overrides.items():
        if override.pending_version is not None:
            override.active_version = override.pending_version
            override.pending_version = None
            # ❌ Didn't sync enabled state to sector config
```

**After** (Fixed):
```python
def check_and_activate_pending(self):
    for sector_name, override in self.overrides.items():
        if override.pending_version is not None:
            override.active_version = override.pending_version
            override.pending_version = None

            # ✅ Sync state to sector config
            if sector_name in self.sectors:
                self.sectors[sector_name].enabled = override.enabled
                if override.tickers is not None:
                    self.sectors[sector_name].symbols = override.tickers
```

**Result**: Activation now properly enables sectors for trading

---

## Storage Structure

### Universe Overrides File
**Location**: `out/universe_overrides.json`

```json
{
  "sectors": {
    "energy": {
      "enabled": true,
      "active_version": 1,
      "pending_version": null,
      "last_modified": "2026-01-14T16:20:00.000000+00:00",
      "tickers": ["EOSE", "MPLX"]
    }
  },
  "registry_version": 1,
  "last_saved": "2026-01-14T16:20:00.000000+00:00"
}
```

**Key Fields**:
- `enabled`: Whether sector is active for trading
- `active_version`: Current active version
- `pending_version`: Staged version (null if no pending changes)
- `tickers`: Symbol list (overrides base config if present)

---

## Complete Workflow Example

### Scenario: Add TSLA to new "robotics" sector

1. **Dashboard**: Candidate for TSLA appears with BUY signal
2. **Click**: "Propose Add" button
3. **UI**: Check "Create new sector"
   - Name: `robotics`
   - Description: `Robotics and automation companies`
4. **Click**: "Create Proposal"
5. **Result**:
   - ✅ Sector "robotics" created (`enabled: false`)
   - ✅ Proposal created to add TSLA
   - ✅ Candidate moved to History tab
6. **Approve**: Click "Approve" in Universe Advisor panel
7. **Result**:
   - ✅ Proposal status="APPROVED"
   - ✅ `pending_version: 1` staged
8. **Next Loop** (within the hour):
   - ✅ Activation promotes version
   - ✅ TSLA added to robotics sector
   - ✅ Robotics sector enabled
   - ✅ TSLA appears in trading universe
9. **Trading**:
   - ✅ Signals generated for TSLA
   - ✅ Orders placed on Alpaca

---

## Verification

### Check Loaded Sectors
```python
from pathlib import Path
from src.app.universe_registry import UniverseRegistry

registry = UniverseRegistry(
    Path("config/config.yaml"),
    Path("out/universe_overrides.json")
)

# List all sectors (base + UI-created)
for name, sector in registry.sectors.items():
    print(f"{name}: enabled={sector.enabled}, symbols={len(sector.symbols)}")
```

### Check Trading Universe
```python
resolution = registry.resolve()
print(f"Total symbols: {len(resolution.symbols)}")
print(f"Symbols: {', '.join(sorted(resolution.symbols))}")
```

---

## Benefits

### ✅ **Zero Manual Configuration**
- No `config.yaml` edits required
- No file system access needed
- Pure UI workflow

### ✅ **Immediate Feedback**
- See sector created instantly
- Track proposal status in real-time
- Automatic activation on next loop

### ✅ **Persistent Storage**
- Sectors survive restarts
- Overrides file is source of truth
- Changes tracked with versions

### ✅ **Audit Trail**
- Proposal history logged
- Timestamps for all changes
- Can see who approved what

---

## Troubleshooting

### Sector Not Trading?

**Check 1**: Is sector enabled?
```bash
curl http://localhost:8000/universe/sectors | jq '.sectors[] | select(.sector_name=="energy")'
```

**Check 2**: Is there a pending version?
```json
{
  "enabled": true,
  "pending_version": 2  // ← Waiting for activation
}
```
→ Wait for next loop iteration

**Check 3**: Is sector in active universe?
```bash
cat out/universe_active.json
```

**Check 4**: Check loop logs
```bash
tail -f logs/loop/loop_$(date +%Y%m%d).log
```

---

## Limitations

### Base Config Still Preferred
- For **permanent sectors** (core holdings), still add to `config.yaml`
- Override file is for **operator experiments**
- Base config = team-wide defaults
- Overrides = personal customizations

### No Description Editing
- Sector description is set at creation
- To change: Delete sector and recreate
- OR: Manually edit `config.yaml`

### Single-Operator System
- Overrides file is not multi-user
- Last write wins (no conflict resolution)
- For teams: Use PR workflow with `config.yaml`

---

## Comparison: Before vs After

### Before (Broken)
```
1. Create sector via UI
2. ❌ Sector ignored: "unknown sector"
3. ❌ Need manual config.yaml edit
4. ❌ Need loop restart
5. ❌ Multi-step manual process
```

### After (Automatic)
```
1. Create sector via UI
2. ✅ Sector immediately recognized
3. ✅ Approve proposal in UI
4. ✅ Auto-activated next loop
5. ✅ Trading starts automatically
```

---

## Implementation Date
**January 14, 2026**

## Status
✅ **Feature Complete and Tested**

## Commit
`73863ee` - fix(universe): make UI-created sectors work automatically
