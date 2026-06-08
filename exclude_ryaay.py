"""Exclude RYAAY from trading due to availability issues."""

from src.app.ticker_exclusions import TickerExclusionManager

manager = TickerExclusionManager()

# Add RYAAY exclusion
manager.add_exclusion(
    symbol="RYAAY",
    action="exclude",
    confidence=1.0,
    rationale="Insufficient qty available for order - Alpaca ADR borrow constraints causing repeated order failures",
    ttl_hours=720,  # 30 days
    categories=["broker_constraint", "availability"],
    source="manual",
)

print("RYAAY excluded from trading for 30 days")
print(f"Exclusions: {list(manager.get_all_exclusions().keys())}")
