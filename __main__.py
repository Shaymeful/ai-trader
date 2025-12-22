"""Entry point to run from repo root with 'python -m ai-trader' or 'python .'"""

from src.app.__main__ import run_trading_loop

if __name__ == "__main__":
    run_trading_loop()
