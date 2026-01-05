"""Allow running selector as: python -m src.app.selector.run_once"""

from src.app.selector.run_once import main

if __name__ == "__main__":
    import sys

    sys.exit(main())
