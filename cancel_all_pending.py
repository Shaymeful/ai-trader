"""Cancel all pending orders."""
from src.app.config import load_config_with_yaml, get_alpaca_credentials
from src.broker import AlpacaBroker

config = load_config_with_yaml()
api_key, secret_key, trading_base_url, _ = get_alpaca_credentials('paper')
broker = AlpacaBroker(api_key, secret_key, trading_base_url)

print("Cancelling all open orders...")
count = broker.cancel_all_open_orders()
print(f"Cancelled {count} orders.")
