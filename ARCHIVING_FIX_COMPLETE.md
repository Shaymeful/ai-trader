# Candidate Archiving Fix Complete

## Issue Found

The candidate archiving feature wasn't working because:
1. The dashboard code was trying to use `candidate_id` field
2. The candidates API doesn't return `candidate_id` - only returns symbol, action, confidence, etc.
3. This caused `currentProposeCandidateId` to always be `undefined`
4. When archiving was attempted, nothing happened because the ID didn't exist

## Fix Applied

Changed all references from `candidate_id` to `symbol`:
- Variables renamed: `currentProposeCandidateId` → `currentProposeCandidateSymbol`
- Archiving logic now uses `c.symbol` instead of `c.candidate_id`
- Badge counts now filter by symbol
- Removed `candidate_id` from API request payload (backend doesn't use it)

## Your Energy Sector

**Good news:** Your Energy sector with WEC is still intact! I checked the API and confirmed:
```json
{
    "sector_name": "energy",
    "enabled": true,
    "description": "energy",
    "symbols": ["WEC"],
    "symbol_count": 1
}
```

The sector was never removed - it's in the database and showing up correctly.

## Clearing Old Archived Data

Since the archiving system changed from using IDs to symbols, you should clear your old localStorage data to start fresh:

**Option 1: Via Browser Console (Recommended)**
1. Open http://localhost:8001
2. Press F12 to open Developer Tools
3. Go to Console tab
4. Run: `localStorage.removeItem('archivedCandidates')`
5. Refresh the page

**Option 2: Via Browser Settings**
1. In your browser settings, clear site data for http://localhost:8001
2. Refresh the page

## Testing the Fix

Now when you add a candidate to a sector (new or existing):
1. Click "Propose Add to Sector" on any candidate
2. Either select existing sector OR create new sector
3. Click "Propose Add"
4. **The candidate should immediately move to the History tab**
5. Badge counts should update correctly

## Files Modified

- `src/ui_api/dashboard.html` - Fixed all candidate_id references to use symbol instead

## Commit

```
commit 42238e5
fix(ui): use symbol instead of candidate_id for archiving
```

## Dashboard Status

Dashboard restarted and running at: **http://localhost:8001**

Test it out by trying to add another candidate to a sector!
