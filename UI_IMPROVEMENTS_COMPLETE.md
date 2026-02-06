# UI Improvements Complete

## Changes Made

### 1. Candidates History Tab
Added Active/History tab system to the Candidates section:

**Active Tab:**
- Shows candidates that haven't been added to any sector yet
- Default view when loading the dashboard
- Badge shows count of active candidates

**History Tab:**
- Shows candidates that have been added to sectors
- Automatically populated when you click "Propose Add to Sector"
- Keeps your candidates list clean and organized
- Badge shows count of archived candidates

**Features:**
- History persists across browser sessions using localStorage
- Each tab shows badge count (e.g., "Active 5" / "History 12")
- Filter functionality (action, confidence, search) works within each tab
- Tab styling with active indicator (blue underline)

### 2. Auto-Close Sector Popup
Fixed the "Propose Add to Sector" modal behavior:

**Previous Behavior:**
- Modal stayed open after clicking "Propose Add"
- Required manual close even after success

**New Behavior:**
- Modal closes immediately when candidate is successfully added
- Modal closes after 2 seconds even if there's an error
- Prevents "stuck popup" situation
- Better user experience with automatic cleanup

**Archive Triggers:**
- Candidate archived when added to existing sector via proposal
- Candidate archived when added to new sector during creation
- Works for both BUY and WATCH action candidates

### 3. Data Preservation
**Important:** All your existing sector configurations and tickers are preserved:
- No changes to any sector definitions in `config/universe.yaml`
- No changes to any ticker lists
- History tracking is purely UI-side (localStorage)
- Completely safe update with no data loss

## How to Use

### Viewing Candidates
1. Open dashboard at http://localhost:8001
2. Scroll to Candidates section
3. Click "Active" tab to see candidates you haven't processed yet
4. Click "History" tab to see candidates you've already added to sectors

### Adding Candidates to Sectors
1. Find candidate in Active tab
2. Click "Propose Add to Sector"
3. Select existing sector OR create new sector
4. (Optional) Add rationale
5. Click "Propose Add"
6. **Popup automatically closes**
7. **Candidate automatically moves to History tab**

### Managing History
- History is stored in your browser's localStorage
- Persists across browser restarts
- Each browser/device has its own history
- To clear history: Open browser console and run `localStorage.removeItem('archivedCandidates')`

## Technical Details

### Files Modified
- `src/ui_api/dashboard.html` - Added tabs, history tracking, auto-close logic

### New JavaScript Functions
- `loadArchivedCandidates()` - Loads history from localStorage on startup
- `saveArchivedCandidates()` - Saves history to localStorage
- `archiveCandidate(candidateId)` - Moves candidate to history
- `switchCandidatesTab(tab)` - Switches between Active/History tabs
- `updateCandidatesBadges()` - Updates badge counts on tabs

### Modified Functions
- `renderCandidates()` - Now filters by active/history based on current tab
- `submitProposeAdd()` - Archives candidate on success and auto-closes modal
- `loadDashboard()` - Loads archived candidates from localStorage on init

### CSS Added
- `.candidates-tabs` - Tab container styling
- `.candidates-tab` - Individual tab button styling
- `.tab-badge` - Badge count styling
- `.candidates-tab.active` - Active tab indicator (blue)

## Testing Recommendations

1. **Test Active Tab:**
   - Verify active candidates show in Active tab
   - Verify badge count matches number of rows

2. **Test History Tab:**
   - Add a candidate to a sector
   - Verify it moves to History tab immediately
   - Verify badge count updates

3. **Test Popup Auto-Close:**
   - Add candidate to existing sector → should close immediately
   - Create new sector with candidate → should close immediately
   - Try with invalid input (no sector selected) → should show error and close after 2s

4. **Test Persistence:**
   - Add candidates to History
   - Refresh browser
   - Verify History tab still shows archived candidates

5. **Test Filters:**
   - Apply action filter in Active tab
   - Switch to History tab
   - Verify filter still works

## Dashboard Access

The dashboard has been restarted and is running at:
**http://localhost:8001**

Both the loop and dashboard are running:
- Loop: PID 49428 (paper trading, 10-minute interval)
- Dashboard: PID 54428 (port 8001)

## Rollback Instructions

If you need to rollback these changes:
```bash
cd /c/dev/ai-trader
git revert 269b17c
powershell -Command "Get-Process python | Stop-Process -Force"
nohup .venv/Scripts/python.exe -m uvicorn src.ui_api.app:app --host 0.0.0.0 --port 8001 >> logs/dashboard.log 2>&1 &
```

Note: Rolling back will not affect your sector configurations or existing tickers.
