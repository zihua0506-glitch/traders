"""CLI: fetch and persist index component stocks.

No arguments; updates S&P 500 and Nasdaq-100 constituents in `sentiment.db`.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import configure_logging
from collectors.indices import fetch_all_indices
from db import get_index_stocks


def main() -> int:
    configure_logging()

    print("=" * 60)
    print("Index Stock Updater")
    print("=" * 60)

    results = fetch_all_indices()

    print("\nSaved (processed) components:")
    for name in ("sp500", "nasdaq100"):
        print(f"  {name}: {int(results.get(name, 0))}")

    total_unique = len(get_index_stocks())
    sp500_membership = len(get_index_stocks("sp500"))
    nasdaq100_membership = len(get_index_stocks("nasdaq100"))

    print("\nDatabase summary:")
    print(f"  total_unique_tickers: {total_unique}")
    print(f"  sp500: {sp500_membership}")
    print(f"  nasdaq100: {nasdaq100_membership}")
    print("=" * 60)

    if sp500_membership <= 0 or nasdaq100_membership <= 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

