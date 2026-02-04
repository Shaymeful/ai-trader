# PR Summary: Aggressive Tech+Energy Daytrade Mode

## Overview

Added "Trading Mode Profiles" feature enabling coordinated configuration switching between "Normal" and "Aggressive Tech+Energy Daytrade" modes. This feature coordinates changes across strategies, universe sectors, selector thresholds, and AI Co-Pilot features with a single mode switch.

## Motivation

Previously, users had to manually adjust multiple disconnected settings to switch trading styles:
- Enable/disable strategies individually
- Toggle universe sectors one by one
- Edit selector thresholds in yaml files
- Configure AI Co-Pilot features separately

This PR introduces **mode profiles** that coordinate all these settings, making it easy to switch between balanced trading and aggressive tech/energy daytrade with a single click.

## What's New

### 1. Mode Profiles Configuration (`config/modes.yaml`)

Defines two profiles:
- **Normal**: Balanced trading with standard risk controls
- **Aggressive Tech+Energy Daytrade**: High-frequency tech/energy focus with dynamic ticker management

Each profile specifies coordinated settings for:
- Strategy enable/weight/params
- Universe sector toggles
- Selector thresholds (confidence, TTL, max candidates)
- AI Co-Pilot feature flags

### 2. Universe Ticker Manager (New AI Co-Pilot Feature)

New AI advisor that dynamically recommends:
- **add_candidates**: New tech/battery/energy tickers to add to universe
- **remove_candidates**: Underperforming tickers to remove
- **buy_bias**: Existing tickers to prioritize
- **sell_bias**: Current positions to consider selling

Enabled in Aggressive mode to redirect AI "thinking power" from strategy critique toward actionable ticker decisions.

**Safety**: Advisory only, logged to `logs/ticker_manager/recommendations.jsonl`

### 3. Selector Runtime Overrides (`data/selector_overrides.json`)

New mechanism to override `config/selector.yaml` settings at runtime:
- Aggressive mode: Lower confidence (0.52), more candidates (80), shorter TTL (90min)
- Normal mode: Conservative defaults (0.65 confidence, 40 candidates, 180min TTL)

Follows existing pattern of `ui_runtime_overrides.json` and `strategies_overrides.json`.

### 4. Dashboard UI Mode Selector

Added prominent mode selector control with:
- Two-button toggle (Normal / Aggressive)
- Active mode badge
- Profile description
- Visual feedback on mode switch
- Coordinated changes list (shows what will change)

### 5. API Endpoints

- **POST /api/mode**: Switch mode profile
  - Coordinates strategy, universe, selector, AI Co-Pilot changes
  - Returns pending version numbers
  - Respects pause_trading.flag safety gate

- **GET /api/mode**: Get current mode status
  - Returns active profile, available profiles, coordinated settings

### 6. Enabled Constituent Removals

Updated `config/config.yaml`:
- `allow_constituent_removals: true` (was false)
- Safety gates: max_remove_per_run: 1, min_confidence_remove: 0.85
- Now visible in UI for Aggressive mode ticker management

## Files Changed

### New Files (6)
```
config/modes.yaml                                 # Mode profile definitions
src/app/selector_overrides.py                     # Selector override loader
src/app/llm_advisors/universe_ticker_manager.py   # New AI advisor
tests/test_mode_profiles.py                       # Mode switching tests
tests/test_selector_overrides.py                  # Selector override tests
PR_SUMMARY_MODE_PROFILES.md                       # This file
```

### Modified Files (5)
```
config/config.yaml                    # Added universe_ticker_manager feature, enabled removals
src/app/config.py                     # Added mode loading functions, universe_ticker_manager fields
src/app/llm_advisors/__init__.py      # Exported UniverseTickerManager
src/ui_api/app.py                     # Added POST /api/mode, GET /api/mode endpoints
src/ui_api/dashboard.html             # Added mode selector UI, CSS, JavaScript
docs/ARCHITECTURE.md                  # Documented mode profiles feature
```

## Testing

### Unit Tests

```bash
# Test mode profiles
pytest tests/test_mode_profiles.py -v

# Test selector overrides
pytest tests/test_selector_overrides.py -v
```

**Expected results:**
- Mode profile loading and switching
- Override persistence across restarts
- Deep merge of nested overrides
- Coordinated setting validation
- Aggressive vs Normal differences

### Manual Testing with curl

#### 1. Get current mode status
```bash
curl -s http://localhost:8000/api/mode | python -m json.tool
```

**Expected output:**
```json
{
  "active_profile": "normal",
  "available_profiles": ["normal", "aggressive_tech_energy"],
  "profile_description": "Balanced trading with standard risk controls...",
  "coordinated_settings": {...}
}
```

#### 2. Switch to Aggressive mode
```bash
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"profile": "aggressive_tech_energy"}' \
  | python -m json.tool
```

**Expected output:**
```json
{
  "status": "success",
  "message": "Mode switched to 'aggressive_tech_energy'. Changes will take effect on next loop iteration.",
  "details": {
    "profile": "aggressive_tech_energy",
    "description": "Aggressive tech+energy daytrade...",
    "pending_versions": [
      "strategy_AI_COPILOT_WEIGHTED_enable_v123",
      "strategy_AI_COPILOT_WEIGHTED_weight_v124",
      "universe_mega_cap_tech_v45"
    ]
  }
}
```

#### 3. Verify coordinated changes took effect

**Check allocation (AI_COPILOT_WEIGHTED should be enabled with 0.35 weight):**
```bash
curl -s http://localhost:8000/allocation | python -m json.tool
```

**Check universe sectors (core_index should be disabled):**
```bash
curl -s http://localhost:8000/universe/sectors | python -m json.tool
```

**Check candidates (should see more candidates with lower confidence):**
```bash
curl -s http://localhost:8000/candidates | python -m json.tool
```

#### 4. Switch back to Normal
```bash
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"profile": "normal"}' \
  | python -m json.tool
```

### Dashboard UI Testing

1. Open http://localhost:8000
2. Locate "Trading Mode" panel (below health panel, above account summary)
3. Observe current mode badge (should show "Normal" in blue)
4. Click "Aggressive Tech+Energy Daytrade" button
5. Observe:
   - Mode badge changes to "Aggressive" (orange)
   - Success notification appears
   - Coordinated changes list shows pending versions (auto-hides after 10s)
6. Wait for next loop iteration (~10 minutes or trigger manually)
7. Verify changes reflected in:
   - Strategies section (AI_COPILOT_WEIGHTED should be enabled)
   - Universe Sectors (core_index disabled, tech/energy enabled)
   - Candidates list (more candidates, lower confidence thresholds)

## Architecture Highlights

### Coordinated Changes Flow

```
User clicks "Aggressive" button
    ↓
JavaScript: switchMode('aggressive_tech_energy')
    ↓
POST /api/mode {profile: "aggressive_tech_energy"}
    ↓
API Endpoint (src/ui_api/app.py):
    1. Load modes.yaml → get profile settings
    2. Save mode override → data/mode_override.json
    3. Update AI_COPILOT_WEIGHTED strategy:
       - StrategyRegistry.update_strategy_enabled(true)
       - StrategyRegistry.update_strategy_weight(0.35)
       - StrategyRegistry.update_strategy_params({execution_enabled: true})
    4. Update universe sectors:
       - UniverseRegistry.update_sector_enabled("mega_cap_tech", true)
       - UniverseRegistry.update_sector_enabled("core_index", false)
    5. Save selector overrides → data/selector_overrides.json
    6. Update AI Co-Pilot features → data/ui_runtime_overrides.json
    ↓
Return {success, pending_versions}
    ↓
Next loop iteration:
    - Loads data/mode_override.json → active_profile = "aggressive_tech_energy"
    - Loads data/selector_overrides.json → aggressive thresholds
    - Applies staged strategy/universe changes
    - Enables universe_ticker_manager AI advisor
    ↓
Trading now in Aggressive mode!
```

### Safety Gates

1. **Trading Pause**: If `state/pause_trading.flag` exists, mode switch saves profile but warns execution remains disabled
2. **Staged Activation**: All changes staged via StrategyRegistry/UniverseRegistry versioning
3. **No Auto-Execution**: Universe ticker manager recommendations are logged, not auto-applied
4. **Constituent Removal Limits**: max_remove_per_run: 1, min_confidence_remove: 0.85

### Configuration Precedence

```
Runtime Overrides (highest priority)
    ↓
Mode Profile (modes.yaml)
    ↓
Base Config (config.yaml, selector.yaml, strategies.yaml)
    ↓
Hardcoded Defaults (lowest priority)
```

## Future Enhancements

1. **Additional Profiles**: Conservative, Swing Trade, Earnings Play, Volatility Trading
2. **Auto Mode Switching**: Switch modes based on market conditions (VIX, volume, time of day)
3. **Profile Customization**: Allow users to create custom profiles via UI
4. **Backtest Profiles**: Compare performance across modes using historical data
5. **Profile Scheduling**: Time-based mode switching (aggressive during market open, normal mid-day)

## Repo Rules Compliance

### Spec Sync Rule ✓
- Updated `docs/ARCHITECTURE.md` with full mode profiles documentation
- Documented new API endpoints, configuration files, and behavior

### Safety + Correctness ✓
- Mode switching respects `pause_trading.flag`
- Constituent removals have strict safety limits
- All changes staged via existing Registry pattern
- Advisory-only AI recommendations

### Testing ✓
- Unit tests for mode switching logic
- Unit tests for selector override merging
- Manual curl test commands provided
- Dashboard UI testing procedure documented

## Migration Notes

**No breaking changes.** Existing installations will:
- Use "normal" profile by default
- Respect existing strategy/universe/AI Co-Pilot settings
- Continue functioning without modes.yaml (falls back to defaults)

To start using mode profiles:
1. Pull latest changes
2. Restart dashboard API server
3. Open dashboard → see new "Trading Mode" panel
4. Switch to Aggressive mode via UI or API

## Questions for Review

1. **Profile naming**: Is "aggressive_tech_energy" descriptive enough? Alternative: "tech_energy_daytrade"?
2. **UI placement**: Mode selector is below health panel. Should it be higher (header area)?
3. **Auto-enable**: Should Aggressive mode auto-enable after first install, or stay in Normal?
4. **Ticker manager integration**: Should recommendations auto-populate as proposals, or stay logs-only?

## Acknowledgments

This feature follows the existing patterns established in:
- StrategyRegistry (staged changes, versioning)
- UniverseRegistry (sector toggles, safe activation)
- ui_runtime_overrides.json (runtime config changes)
- AI Co-Pilot architecture (advisory-only, budget-limited)

Thanks to the existing architecture for making this feature relatively straightforward to implement!
