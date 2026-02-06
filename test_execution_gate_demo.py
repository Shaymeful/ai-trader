"""Demo script to test execution gate with real symbols."""

from decimal import Decimal
from pathlib import Path

from src.app.config import get_active_mode_profile, load_mode_profiles
from src.app.execution.tradability_filter import ExecutionGateConfig, TradabilityGate
from src.market_data.fundamentals_cache import FundamentalsCache

# Initialize
print("=" * 80)
print("EXECUTION GATE DEMO")
print("=" * 80)
print()

# Load active mode
modes_config = load_mode_profiles()
active_profile_name, active_profile = get_active_mode_profile(modes_config)

print(f"Active mode: {active_profile_name}")
print(f"Description: {active_profile.get('description', 'N/A')}")
print()

# Check if execution gate configured
if "execution_gate" not in active_profile:
    print("No execution gate configured in active mode.")
    print("Switch to small_cap_swing mode to test the gate.")
    exit(0)

# Load execution gate
gate_config = ExecutionGateConfig.from_dict(active_profile["execution_gate"])
fundamentals_cache = FundamentalsCache()
gate = TradabilityGate(gate_config, fundamentals_cache)

print()
print("Execution Gate Configuration:")
print(f"  Market cap range: ${gate_config.min_market_cap_usd:,.0f} - ${gate_config.max_market_cap_usd:,.0f}")
print(f"  Price range: ${gate_config.min_price:.2f} - ${gate_config.max_price:.2f}")
print(f"  Min liquidity: ${gate_config.min_avg_dollar_volume_20d:,.0f}/day")
print(f"  Max spread: {gate_config.max_spread_bps:.0f} bps")
print(f"  Strict mode: {gate_config.strict_mode}")
print()

# Test symbols
test_symbols = [
    ("AAPL", Decimal("180.00"), "Mega cap tech"),
    ("NVDA", Decimal("500.00"), "Mega cap tech"),
    ("MSFT", Decimal("380.00"), "Mega cap tech"),
    ("META", Decimal("450.00"), "Mega cap tech"),
    ("TSLA", Decimal("250.00"), "Large cap tech"),
    ("AMD", Decimal("120.00"), "Large cap tech"),
    ("PLTR", Decimal("22.00"), "Mid cap tech"),
    ("AFRM", Decimal("35.00"), "Small/mid cap fintech"),
    ("SOFI", Decimal("8.50"), "Small cap fintech"),
    ("IONQ", Decimal("18.00"), "Small cap quantum"),
    ("RIVN", Decimal("11.00"), "Mid cap EV"),
    ("SPY", Decimal("480.00"), "ETF - mega cap"),
    ("QQQ", Decimal("420.00"), "ETF - mega cap"),
]

print("=" * 80)
print("TESTING EXECUTION GATE")
print("=" * 80)
print()

allowed_count = 0
blocked_count = 0

for symbol, price, description in test_symbols:
    result = gate.check_tradability(symbol, price)

    status = "[ALLOWED]" if result.allowed else "[BLOCKED]"

    print(f"{symbol:<6} @ ${price:>7.2f} - {description:<30} {status}")

    if not result.allowed:
        print(f"       Reason: {result.message}")
        blocked_count += 1
    else:
        allowed_count += 1
    print()

print("=" * 80)
print(f"Summary: {allowed_count} allowed, {blocked_count} blocked")
print("=" * 80)
