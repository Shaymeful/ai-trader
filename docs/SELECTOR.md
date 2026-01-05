# RSS Selector - Automation & Energy Sectors

## Overview

The RSS Selector is a rules-based candidate generation system that monitors automation and energy sector news feeds to identify potential trading opportunities.

**Key Features:**
- **Targeted Sectors**: Automation and Energy
- **Conservative Symbol Extraction**: Only explicit patterns `(SYMBOL)`, `SYMBOL:`, `$SYMBOL`
- **Sentiment Analysis**: Maps headlines to buy/sell/watch actions
- **Confidence Scoring**: Quantifies signal strength (0.60-0.90)
- **Safety First**: Selector NEVER places orders - only generates candidates
- **No Network in Tests**: All tests use fixtures for reliability

## Architecture

```
RSS Feeds
    ↓
Selector (src/app/selector/)
    ├─ Fetch & Parse RSS
    ├─ Classify Sector (automation/energy)
    ├─ Extract Symbol (conservative patterns)
    ├─ Map Action (buy/sell/watch)
    └─ Compute Confidence (base + bonuses - penalties)
    ↓
Output Files
    ├─ out/selector/snapshot.json (current candidates)
    └─ out/selector/events.jsonl (processing log)
    ↓
Trading Loop (src/app/runner.py)
    └─ Reads snapshot.json and generates orders
```

## Configuration

### Config File: `config/selector.yaml`

**Sectors Enabled:**
```yaml
sectors_enabled:
  - automation
  - energy
```

**RSS Feeds:**
```yaml
rss_feeds:
  - https://example.com/automation
  - https://example.com/energy
  # Add your preferred RSS feed URLs here
```

**Keyword Rules:**

Automation keywords:
- `automation`, `robot`, `robotics`, `warehouse`, `logistics`
- `PLC`, `industrial`, `manufacturing`, `factory`
- `sorting`, `conveyor`, `AI automation`, `automated`
- `AGV`, `SCADA`, `IoT manufacturing`

Energy keywords:
- `energy`, `oil`, `gas`, `lng`, `solar`, `wind`
- `nuclear`, `battery`, `grid`, `power`, `utility`
- `renewable`, `pipeline`, `crude`, `refinery`
- `petrochemical`, `drilling`

**Action Keywords:**

Buy signals:
- `beats`, `raises guidance`, `upgrades`, `contract`, `award`
- `record revenue`, `exceeds`, `strong quarter`, `outperforms`
- `acquisition`, `partnership`, `breakthrough`

Sell signals:
- `misses`, `cuts guidance`, `downgrades`, `investigation`
- `bankruptcy`, `layoffs`, `lawsuit`, `recall`, `warning`
- `slump`, `plunge`, `tumbles`

**Confidence Modifiers:**
```yaml
confidence_modifiers:
  base_confidence: 0.55
  strong_keyword_bonus: 0.10  # Per keyword match
  max_confidence: 0.90
  uncertain_symbol_penalty: 0.15  # When symbol extraction uncertain
```

**Safety Settings:**
```yaml
safety:
  action_default_when_uncertain: watch  # Default action if sentiment unclear
  max_candidates_per_run: 50  # Limit total candidates
  require_symbol_allowlist: false  # Set true to only allow specific symbols
  symbol_allowlist: []  # Whitelist (if require_symbol_allowlist: true)
  symbol_denylist: []  # Blacklist (always excluded)
```

## How It Works

### 1. Sector Classification

The selector counts keyword matches for each sector and selects the highest scoring sector (if > 0).

**Example:**
```
Headline: "Rockwell Automation (ROK) launches new PLC for factory automation"
Keywords matched:
  - automation (×2)
  - PLC (×1)
  - factory (×1)
Sector: automation (4 matches)
```

### 2. Symbol Extraction (Conservative)

The selector uses a strict regex pattern to extract symbols:

**Accepted Patterns:**
- Parentheses: `(ROK)`, `(XOM)`, `(NEE)`
- Colon: `TSLA:`, `ENPH:`
- Dollar sign: `$AAPL`, `$MSFT`

**Validation:**
- 1-5 uppercase letters only
- Must match explicit pattern (no guessing)

**Example:**
```
✓ "Rockwell Automation (ROK) beats earnings" → Symbol: ROK, Certain: True
✓ "TSLA: Tesla expands automation" → Symbol: TSLA, Certain: True
✗ "General Electric misses guidance" → Symbol: None, Certain: False
✗ "Company (abc) announces news" → Symbol: None (lowercase rejected)
```

### 3. Action Mapping

The selector counts buy/sell keyword matches and prioritizes sell signals (negative news).

**Priority:**
1. Sell signals (if any) → `sell`
2. Buy signals (if any) → `buy`
3. Default → `watch`

**Example:**
```
Headline: "NextEra Energy (NEE) raises guidance on strong solar growth"
Buy keywords: raises guidance, strong
Sell keywords: (none)
Action: buy
```

### 4. Confidence Scoring

**Formula:**
```
confidence = base_confidence + (keyword_count × bonus) - uncertainty_penalty
confidence = clamp(confidence, min_confidence, max_confidence)
```

**Parameters:**
- `base_confidence`: 0.55
- `strong_keyword_bonus`: 0.10 per keyword
- `max_confidence`: 0.90
- `uncertain_symbol_penalty`: 0.15 (if symbol extraction fails)
- `min_confidence`: 0.60

**Example:**
```
Headline: "ExxonMobil (XOM) beats Q4 earnings with record oil production"
Action: buy
Keywords matched: beats, beat, record revenue (3)
Symbol certain: Yes

Calculation:
  Base: 0.55
  + 3 keywords × 0.10 = 0.30
  - 0 (symbol certain) = 0.00
  = 0.85
  Clamped: max(0.60, min(0.85, 0.90)) = 0.85
```

### 5. Output Files

**Snapshot: `out/selector/snapshot.json`**
```json
{
  "generated_at": "2026-01-05T10:00:00-05:00",
  "count": 5,
  "candidates": [
    {
      "candidate_id": "rss-20260105100000-ROK",
      "created_at": "2026-01-05T10:00:00-05:00",
      "expires_at": "2026-01-05T13:00:00-05:00",
      "symbol": "ROK",
      "action": "buy",
      "confidence": 0.85,
      "horizon": "intraday",
      "sector": "automation",
      "event_type": "rss_headline",
      "tags": ["automation"],
      "reason": "Rockwell Automation (ROK) beats Q3 earnings with record revenue",
      "avg_dollar_volume": null
    }
  ],
  "metadata": {
    "source": "rss_selector",
    "config": "config/selector.yaml"
  }
}
```

**Events: `out/selector/events.jsonl`**
```json
{"timestamp":"2026-01-05T10:00:00-05:00","event_type":"headline_processed","headline":"Rockwell Automation (ROK) beats...","feed_url":"https://example.com/automation"}
{"timestamp":"2026-01-05T10:00:01-05:00","event_type":"candidate_created","headline":"Rockwell Automation (ROK) beats...","symbol":"ROK","action":"buy","sector":"automation","confidence":0.85}
```

## Usage

### Manual Execution

**Run selector once:**
```bash
python -m src.app.selector.run_once
```

**Output:**
```
RSS Selector - Automation & Energy
==================================================
Loaded config: config\selector.yaml
Enabled sectors: automation, energy
RSS feeds configured: 2

Fetching and processing RSS feeds...
Processed 12 events
Generated 5 candidates

Candidates by action:
  BUY: 2
  SELL: 1
  WATCH: 2

Candidates by sector:
  automation: 3
  energy: 2

Writing snapshot to out/selector/snapshot.json
Appending events to out/selector/events.jsonl

Snapshot size: 1247 bytes

Selector run completed successfully!
```

### Automated Execution (Windows Task Scheduler)

**Install scheduled tasks:**
```powershell
# Run as Administrator
cd C:\dev\ai-trader
.\tools\windows\install_tasks.ps1
```

This creates:
- **AITrader-Selector**: Runs every 15 minutes (8:50 AM - 4:10 PM ET)
- Logs to `logs/selector/selector_YYYYMMDD.log`

**Manual trigger:**
```powershell
.\tools\windows\run_selector.ps1
.\tools\windows\run_selector.ps1 -LogToFile  # With logging
```

### Dashboard Monitoring

**View selector status:**
```
http://localhost:8000/selector/status
```

**Response:**
```json
{
  "last_run": "2026-01-05T10:00:00-05:00",
  "candidates_count": 5,
  "candidates_by_action": {
    "buy": 2,
    "sell": 1,
    "watch": 2
  },
  "last_error": null
}
```

## Adding RSS Feeds

### Step 1: Find RSS Feeds

**Recommended sources:**
- Seeking Alpha: Sector-specific feeds
- Yahoo Finance: Category feeds
- Investing.com: News RSS feeds
- OilPrice.com: Energy-specific news
- Industry publications: Automation World, Control Engineering, etc.

### Step 2: Update Config

Edit `config/selector.yaml`:
```yaml
rss_feeds:
  # Automation feeds
  - https://seekingalpha.com/sector/industrials.xml
  - https://www.automationworld.com/rss.xml

  # Energy feeds
  - https://www.oilprice.com/rss/main
  - https://feeds.finance.yahoo.com/rss/2.0/category-energy
```

### Step 3: Test

```bash
python -m src.app.selector.run_once
```

Verify:
- Candidates are generated
- Sectors are correctly classified
- Symbols are extracted (if present)
- Actions make sense for the headlines

## Troubleshooting

### No Candidates Generated

**Possible causes:**
1. **RSS feeds empty or unreachable**
   - Check: `logs/selector/selector_YYYYMMDD.log` for fetch errors
   - Test: Open feed URL in browser

2. **Headlines don't match sector keywords**
   - Check: Are headlines relevant to automation/energy?
   - Solution: Add more sector keywords to `config/selector.yaml`

3. **Confidence below minimum (0.60)**
   - Check: Do headlines contain action keywords (beats, misses, etc.)?
   - Solution: Lower `min_confidence` in config (not recommended)

4. **Symbols filtered out**
   - Check: `require_symbol_allowlist: true` in config?
   - Check: Symbol in `symbol_denylist`?
   - Solution: Update allowlist/denylist

### Incorrect Sector Classification

**Symptoms:**
- Energy headlines classified as automation (or vice versa)

**Diagnosis:**
```python
from src.app.selector.rss_selector import RSSSelector

selector = RSSSelector()
text = "Your headline here"
sector = selector.classify_sector(text)
print(f"Sector: {sector}")
```

**Solutions:**
1. Add more specific keywords to correct sector
2. Remove ambiguous keywords causing mis-classification
3. Adjust keyword weights (not currently supported)

### Symbol Extraction Issues

**Conservative by design:**
- Only explicit patterns are accepted: `(SYMBOL)`, `SYMBOL:`, `$SYMBOL`
- This prevents false positives but may miss some symbols

**If symbols are missing:**
1. **Check headline format**: Does it use explicit patterns?
2. **Manual extraction**: Consider creating candidates without symbols (action: watch)
3. **Pre-processing**: Request RSS feeds with explicit symbol formatting

### Events Not Logged

**Check:**
```bash
ls out/selector/events.jsonl
tail -20 out/selector/events.jsonl
```

**Common issues:**
1. Permissions: Ensure `out/selector/` is writable
2. Disk space: Check available space
3. Process crashes: Check `logs/selector/*.log` for errors

## Integration with Trading Loop

The trading loop reads `out/selector/snapshot.json` and:

1. **Filters expired candidates** (based on `expires_at`)
2. **Applies risk constraints** (position sizing, max positions, daily loss limits)
3. **Generates orders** (respects `pause_trading.flag`)
4. **Logs decisions** (candidate_id, action taken, reason)

**Loop invocation:**
```bash
python -m src.app.runner --mode paper --loop --sleep-seconds 3600
```

**Candidate TTL (Time-To-Live):**
- `buy`: 180 minutes (3 hours)
- `sell`: 120 minutes (2 hours)
- `watch`: 240 minutes (4 hours)

Expired candidates are ignored by the loop.

## Safety Features

### 1. Selector Never Places Orders

The selector only writes JSON files. Orders are placed by the trading loop.

### 2. Max Candidates Per Run

Default: 50 candidates maximum per selector run.

Prevents:
- Runaway candidate generation
- Overwhelming the trading loop
- Excessive memory usage

### 3. Symbol Allowlist/Denylist

**Denylist** (always enforced):
```yaml
symbol_denylist:
  - OTCMKTS  # Exclude OTC stocks
  - PINK     # Exclude pink sheets
```

**Allowlist** (optional):
```yaml
require_symbol_allowlist: true
symbol_allowlist:
  - ROK   # Rockwell Automation
  - XOM   # ExxonMobil
  - NEE   # NextEra Energy
```

### 4. Confidence Thresholds

Minimum confidence: 0.60 (default)

Candidates below this threshold are discarded.

### 5. Testing Without Network

All tests use fixtures in `tests/fixtures/`:
- `rss_automation.xml`
- `rss_energy.xml`

Ensures reliable CI/CD without external dependencies.

## Development

### Running Tests

```bash
# All selector tests
pytest tests/test_selector.py -v

# Specific test class
pytest tests/test_selector.py::TestSectorClassification -v

# Full test suite
pytest
```

### Code Location

```
src/app/selector/
├── __init__.py
├── rss_selector.py      # Core selector logic
├── run_once.py          # CLI entry point
└── __main__.py          # Module entry

tests/
├── test_selector.py     # Unit tests
└── fixtures/
    ├── rss_automation.xml
    └── rss_energy.xml
```

### Adding New Sectors

1. Add sector to `config/selector.yaml`:
   ```yaml
   sectors_enabled:
     - automation
     - energy
     - aerospace  # New sector
   ```

2. Define keyword rules:
   ```yaml
   keyword_rules:
     aerospace:
       tags: [aerospace]
       keywords:
         - aerospace
         - aviation
         - aircraft
         - satellite
         - defense
   ```

3. Add test fixtures:
   - Create `tests/fixtures/rss_aerospace.xml`
   - Add tests in `tests/test_selector.py`

4. Run tests:
   ```bash
   pytest tests/test_selector.py -v
   ```

## FAQ

**Q: Can the selector trade multiple sectors simultaneously?**
A: Yes. Configure multiple sectors in `sectors_enabled` and the selector will classify headlines into the appropriate sector.

**Q: What happens if no symbol is found?**
A: The candidate is still created with `symbol: null` and `action: watch` (or as determined by sentiment). The trading loop may skip these candidates.

**Q: Can I use the selector for live trading?**
A: The selector generates candidates. The trading loop places orders. Set loop to `--mode paper` or use `--dry-run` for safety.

**Q: How do I monitor selector performance?**
A: Check dashboard at `http://localhost:8000/selector/status` or review logs in `logs/selector/*.log`.

**Q: Can I customize confidence scoring?**
A: Yes. Adjust `confidence_modifiers` in `config/selector.yaml`. Be cautious with changes - lower thresholds may generate low-quality candidates.

**Q: Does the selector support non-US markets?**
A: The selector is timezone-aware (uses America/New_York). For non-US markets, you would need to:
1. Add market-specific RSS feeds
2. Adjust keywords for sector classification
3. Update timezone handling if needed

**Q: How often should the selector run?**
A: Default: Every 15 minutes during market hours (8:50 AM - 4:10 PM ET). This balances freshness with API rate limits.

## Next Steps

1. **Configure RSS feeds** in `config/selector.yaml`
2. **Test manually**: `python -m src.app.selector.run_once`
3. **Install scheduled tasks**: `.\tools\windows\install_tasks.ps1`
4. **Monitor dashboard**: `http://localhost:8000/selector/status`
5. **Review candidates**: `cat out/selector/snapshot.json`
6. **Integrate with loop**: See `docs/LOOP_MODE_GUIDE.md`

## Related Documentation

- `docs/ARCHITECTURE.md` - Overall system architecture
- `docs/LOOP_MODE_GUIDE.md` - Trading loop configuration
- `config/selector.yaml` - Selector configuration
- `CLAUDE.md` - Repository rules and guidelines
