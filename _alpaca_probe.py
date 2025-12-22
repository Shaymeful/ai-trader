import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

load_dotenv()

key = os.environ.get("ALPACA_API_KEY")
sec = os.environ.get("ALPACA_SECRET_KEY")
if not key or not sec:
    raise SystemExit("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY")

client = StockHistoricalDataClient(key, sec)

eastern = ZoneInfo("America/New_York")
now = datetime.now(eastern)

# End at most recent regular market close (16:00 ET)
end = now.replace(hour=16, minute=0, second=0, microsecond=0)
if now < end:
    end = end - timedelta(days=1)

# Roll back weekends to Friday
while end.weekday() >= 5:
    end = end - timedelta(days=1)

start = end - timedelta(days=5)

req = StockBarsRequest(
    symbol_or_symbols=["AAPL"],
    timeframe=TimeFrame.Minute,
    start=start,
    end=end,
    feed="iex",
)

resp = client.get_stock_bars(req)
bars = resp.data.get("AAPL", [])

print("now_et:", now)
print("start:", start, "end:", end)
print("bars:", len(bars))
if bars:
    print("first:", bars[0].timestamp, "last:", bars[-1].timestamp)
