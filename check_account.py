"""Check Alpaca account status."""
from src.app.config import load_config_with_yaml, get_alpaca_credentials
from src.broker import AlpacaBroker

config = load_config_with_yaml()
api_key, secret_key, trading_base_url, _ = get_alpaca_credentials('paper')
broker = AlpacaBroker(api_key, secret_key, trading_base_url)
account = broker.client.get_account()

print("\n" + "="*80)
print("ALPACA PAPER ACCOUNT STATUS")
print("="*80)
print(f"Account Status: {account.status}")
print(f"Equity: ${float(account.equity):,.2f}")
print(f"Cash: ${float(account.cash):,.2f}")
print(f"Buying Power: ${float(account.buying_power):,.2f}")
print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
print(f"Daytrading Buying Power: ${float(account.daytrading_buying_power):,.2f}")
print(f"Regt Buying Power: ${float(account.regt_buying_power):,.2f}")
print(f"Pattern Day Trader: {account.pattern_day_trader}")
print(f"Trading Blocked: {account.trading_blocked}")
print(f"Account Blocked: {account.account_blocked}")
print(f"Transfers Blocked: {account.transfers_blocked}")
print("="*80)

if float(account.buying_power) == 0:
    print("\nDIAGNOSIS: Account has $0 buying power!")
    print("This prevents ANY orders from being placed.")
    print("\nPossible causes:")
    print("  1. Account is in a restricted state")
    print("  2. Pattern day trader restrictions")
    print("  3. Alpaca paper account needs reset")
    print("\nSolution: Check Alpaca dashboard or reset paper account")
print()
