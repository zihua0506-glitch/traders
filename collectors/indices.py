"""Index components collector module.

Fetches S&P 500 and Nasdaq 100 component stocks from Wikipedia.
"""

from __future__ import annotations

import io
import logging
import re
import urllib3
from typing import List, Dict

import pandas as pd
import requests

# Suppress SSL warnings for Wikipedia scraping on macOS
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from db import save_index_stock, get_index_stocks, IndexStock


logger = logging.getLogger(__name__)

# Wikipedia URLs for index components
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100#Components"

# User agent to avoid 403 from Wikipedia
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_FOOTNOTE_RE = re.compile(r"\[\d+\]")


def _clean_text(value: object) -> str | None:
    """Normalize table cell text (strip, drop NaN/empty, remove footnotes)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return _FOOTNOTE_RE.sub("", text).strip() or None


def _find_col(df: pd.DataFrame, needle: str) -> object | None:
    """Find the first column whose name contains the given needle (case-insensitive)."""
    needle_lc = needle.lower()
    for col in df.columns:
        if needle_lc in str(col).lower():
            return col
    return None


def _fetch_html(url: str) -> str:
    """Fetch HTML content with proper headers."""
    headers = {"User-Agent": USER_AGENT}
    # verify=False handles macOS SSL certificate issues
    resp = requests.get(url, headers=headers, timeout=30, verify=False)
    resp.raise_for_status()
    return resp.text


def fetch_sp500_tickers() -> List[Dict[str, str | None]]:
    """Fetch S&P 500 component tickers from Wikipedia.

    Returns:
        List of dicts with keys: ticker, company_name, sector, industry
    """
    logger.info("Fetching S&P 500 components from Wikipedia...")

    try:
        html = _fetch_html(SP500_URL)
        tables = pd.read_html(io.StringIO(html))
        # First table contains the current components
        df = tables[0]

        stocks: List[Dict[str, str | None]] = []
        for _, row in df.iterrows():
            ticker = _clean_text(row.get("Symbol"))
            if not ticker:
                continue
            stocks.append(
                {
                    "ticker": ticker,
                    "company_name": _clean_text(row.get("Security")) or "",
                    "sector": _clean_text(row.get("GICS Sector")),
                    "industry": _clean_text(row.get("GICS Sub-Industry")),
                }
            )

        logger.info("Found %d S&P 500 components", len(stocks))
        return stocks

    except Exception as e:
        logger.error("Failed to fetch S&P 500 from Wikipedia: %s", e)
        return []


def fetch_nasdaq100_tickers() -> List[Dict[str, str | None]]:
    """Fetch Nasdaq 100 component tickers from Wikipedia.

    Returns:
        List of dicts with keys: ticker, company_name, sector, industry
    """
    logger.info("Fetching Nasdaq 100 components from Wikipedia...")

    try:
        html = _fetch_html(NASDAQ100_URL)
        tables = pd.read_html(io.StringIO(html))
        # Find the table with Company and Ticker columns
        df = None
        for table in tables:
            cols = [str(c).strip().lower() for c in table.columns]
            if "ticker" in cols and ("company" in cols or "security" in cols):
                df = table
                break

        if df is None:
            logger.warning("Could not find Nasdaq 100 components table")
            return []

        gics_sector_col = _find_col(df, "GICS Sector")
        gics_subindustry_col = _find_col(df, "GICS Sub-Industry")
        icb_industry_col = _find_col(df, "ICB Industry")
        icb_subsector_col = _find_col(df, "ICB Subsector")

        stocks: List[Dict[str, str | None]] = []
        for _, row in df.iterrows():
            ticker = _clean_text(row.get("Ticker") or row.get("Symbol"))
            company = _clean_text(row.get("Company") or row.get("Security")) or ""

            sector_raw = None
            if gics_sector_col is not None:
                sector_raw = row.get(gics_sector_col)
            elif icb_industry_col is not None:
                sector_raw = row.get(icb_industry_col)
            sector = _clean_text(sector_raw)

            industry_raw = None
            if gics_subindustry_col is not None:
                industry_raw = row.get(gics_subindustry_col)
            elif icb_subsector_col is not None:
                industry_raw = row.get(icb_subsector_col)
            industry = _clean_text(industry_raw)

            if ticker:
                stocks.append({
                    "ticker": ticker,
                    "company_name": company,
                    "sector": sector,
                    "industry": industry,
                })

        logger.info("Found %d Nasdaq 100 components", len(stocks))
        return stocks

    except Exception as e:
        logger.error("Failed to fetch Nasdaq 100 from Wikipedia: %s", e)
        return []


def fetch_and_save_index(index_name: str, fetch_func) -> int:
    """Fetch index components and save to database.

    Args:
        index_name: Index identifier (sp500, nasdaq100)
        fetch_func: Function to fetch tickers

    Returns:
        Number of stocks saved
    """
    stocks = fetch_func()
    if not stocks:
        return 0

    saved = 0
    total = len(stocks)

    progress_every = 25 if total >= 200 else 10
    for i, stock in enumerate(stocks, 1):
        ticker = stock["ticker"]
        if i == 1 or i == total or i % progress_every == 0:
            logger.info("[%d/%d] Processing %s...", i, total, ticker)
        else:
            logger.debug("[%d/%d] Processing %s...", i, total, ticker)

        success = save_index_stock(
            ticker=ticker,
            company_name=stock["company_name"],
            index_name=index_name,
            sector=stock.get("sector"),
            industry=stock.get("industry"),
        )

        if success:
            saved += 1

    logger.info("Saved %d/%d stocks for %s", saved, total, index_name)
    return saved


def fetch_sp500() -> int:
    """Fetch and save S&P 500 components."""
    return fetch_and_save_index("sp500", fetch_sp500_tickers)


def fetch_nasdaq100() -> int:
    """Fetch and save Nasdaq 100 components."""
    return fetch_and_save_index("nasdaq100", fetch_nasdaq100_tickers)


def fetch_all_indices() -> Dict[str, int]:
    """Fetch and save all index components.

    Returns:
        Dict mapping index name to number of stocks saved
    """
    results = {}
    results["sp500"] = fetch_sp500()
    results["nasdaq100"] = fetch_nasdaq100()
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch and save index component stocks (S&P 500, Nasdaq 100)"
    )
    parser.add_argument(
        "--index",
        choices=["sp500", "nasdaq100", "all"],
        default="all",
        help="Which index to fetch (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    print("=" * 60)
    print("Index Components Collector")
    print("=" * 60)
    print()

    if args.index == "sp500":
        count = fetch_sp500()
        print(f"\nS&P 500: {count} stocks saved")
    elif args.index == "nasdaq100":
        count = fetch_nasdaq100()
        print(f"\nNasdaq 100: {count} stocks saved")
    else:
        results = fetch_all_indices()
        print(f"\nResults:")
        for index_name, count in results.items():
            print(f"  {index_name}: {count} stocks saved")

    # Show summary
    print("\n" + "=" * 60)
    print("Database Summary:")
    sp500_count = len(get_index_stocks("sp500"))
    nasdaq100_count = len(get_index_stocks("nasdaq100"))
    print(f"  S&P 500: {sp500_count} stocks")
    print(f"  Nasdaq 100: {nasdaq100_count} stocks")
    print("=" * 60)
