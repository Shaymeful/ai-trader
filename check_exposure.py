"""Quick script to check current portfolio exposure."""

import sys
from decimal import Decimal

from src.app.config import load_config_with_yaml, get_alpaca_credentials

try:
    # Load config
    config = load_config_with_yaml()

    # Get credentials
    api_key, secret_key, trading_base_url, data_base_url = get_alpaca_credentials("paper")

    # Import AlpacaBroker
    from src.broker import AlpacaBroker

    # Create broker
    broker = AlpacaBroker(api_key, secret_key, trading_base_url)

    # Get positions
    positions = broker.get_positions()

    print("\n" + "=" * 80)
    print("CURRENT PORTFOLIO EXPOSURE")
    print("=" * 80)

    if not positions:
        print("No positions found")
        print(f"\nCurrent exposure: $0.00")
        print(f"Capital cap: ${config.max_positions_notional:,.2f}")
        print(f"Utilization: 0.0%")
        print("\n✅ Portfolio is within cap (no sells needed)")
    else:
        total_exposure = Decimal("0")

        print(f"\n{'Symbol':<10} {'Qty':>8} {'Avg Entry':>12} {'Current':>12} {'Exposure':>15}")
        print("-" * 80)

        for symbol, pos_data in sorted(positions.items()):
            if isinstance(pos_data, dict):
                qty = pos_data.get("qty", 0)
                avg_price = Decimal(str(pos_data.get("avg_entry_price", 0)))
                current_price = Decimal(str(pos_data.get("current_price", avg_price)))
            else:
                qty = getattr(pos_data, "qty", 0)
                avg_price = Decimal(str(getattr(pos_data, "avg_entry_price", 0)))
                current_price = Decimal(str(getattr(pos_data, "current_price", avg_price)))

            exposure = Decimal(qty) * avg_price
            total_exposure += exposure

            print(
                f"{symbol:<10} {qty:>8} ${avg_price:>11.2f} ${current_price:>11.2f} ${exposure:>14,.2f}"
            )

        print("-" * 80)
        print(f"{'TOTAL EXPOSURE:':<45} ${total_exposure:>14,.2f}")

        cap = config.max_positions_notional
        utilization = (total_exposure / cap * 100) if cap > 0 else 0

        print(f"\nCapital cap: ${cap:,.2f}")
        print(f"Utilization: {utilization:.1f}%")

        overage = total_exposure - cap
        if overage > 0:
            print(f"\n⚠️  OVER CAP by ${overage:,.2f}")
            print(f"   Reconciliation will trigger sells on next loop iteration!")
        else:
            print(f"\n✅ Portfolio is within cap (${cap - total_exposure:,.2f} headroom)")

    print("=" * 80)
    print()

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    import traceback

    traceback.print_exc()
    sys.exit(1)
