"""NSE and BSE data fetcher for corporate announcements and actions."""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NSE company symbols
NSE_SYMBOLS = {
    "INFY": "INFOSYS",
    "TCS": "TATA CONSULTANCY SERVICES",
    "WIPRO": "WIPRO",
    "HCL": "HCL TECHNOLOGIES",
    "TECHM": "TECH MAHINDRA",
    "LT": "LARSEN & TOUBRO",
    "RELIANCE": "RELIANCE INDUSTRIES",
    "HDFC": "HDFC BANK",
    "ICICI": "ICICI BANK",
    "AXIS": "AXIS BANK",
}

# BSE company symbols (SENSEX and MIDCAP components)
BSE_SYMBOLS = {
    "SENSEX": "BSE SENSEX 50",
    "RELIANCE": "RELIANCE INDUSTRIES",
    "TCS": "TATA CONSULTANCY SERVICES",
    "HDFC": "HDFC BANK",
    "ICICI": "ICICI BANK",
    "INFY": "INFOSYS",
    "LT": "LARSEN & TOUBRO",
    "ITC": "ITC LIMITED",
    "SBIN": "STATE BANK OF INDIA",
    "MARUTI": "MARUTI SUZUKI",
}


class StockFetcher:
    """Fetch NSE and BSE corporate announcements and actions."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def search_company(self, query: str, exchange: str = "NSE") -> List[Dict[str, str]]:
        """
        Search for companies by name or symbol.
        
        Args:
            query: Search string
            exchange: "NSE" or "BSE"
        
        Returns a list of matching companies with symbol, name and exchange.
        """
        query_lower = query.lower()
        symbols = NSE_SYMBOLS if exchange.upper() == "NSE" else BSE_SYMBOLS
        results = []

        for symbol, name in symbols.items():
            if (query_lower in symbol.lower() or query_lower in name.lower()):
                results.append({"symbol": symbol, "name": name, "exchange": exchange.upper()})

        return results

    def search_all_exchanges(self, query: str) -> List[Dict[str, str]]:
        """
        Search for companies across all exchanges (NSE + BSE).
        
        Returns list of matching companies from both exchanges.
        """
        results = []
        results.extend(self.search_company(query, "NSE"))
        results.extend(self.search_company(query, "BSE"))
        
        # Remove duplicates by (symbol, exchange) while preserving order
        seen = set()
        unique_results = []
        for item in results:
            key = (item["symbol"], item["exchange"])
            if key not in seen:
                seen.add(key)
                unique_results.append(item)
        
        return unique_results

    def get_announcements(self, symbol: str, exchange: str = "NSE") -> List[Dict]:
        """
        Fetch corporate announcements for a given symbol.
        
        Args:
            symbol: Stock symbol
            exchange: "NSE" or "BSE"
        
        Returns list of announcements with id, title, date, and description.
        """
        try:
            logger.info(f"Fetching {exchange} announcements for {symbol}")
            
            # Placeholder - returns empty list
            # In production, you would scrape or call exchange API
            return []
            
        except Exception as e:
            logger.error(f"Error fetching announcements for {symbol} ({exchange}): {e}")
            return []

    def get_corporate_actions(self, symbol: str, exchange: str = "NSE") -> List[Dict]:
        """
        Fetch corporate actions for a given symbol.
        
        Args:
            symbol: Stock symbol
            exchange: "NSE" or "BSE"
        
        Returns list of corporate actions with id, type, title, date, and description.
        """
        try:
            logger.info(f"Fetching {exchange} corporate actions for {symbol}")
            
            # Placeholder - returns empty list
            # In production, you would scrape or call exchange API
            return []
            
        except Exception as e:
            logger.error(f"Error fetching corporate actions for {symbol} ({exchange}): {e}")
            return []

    def validate_symbol(self, symbol: str, exchange: str = "NSE") -> bool:
        """Check if symbol exists in the exchange."""
        symbols = NSE_SYMBOLS if exchange.upper() == "NSE" else BSE_SYMBOLS
        return symbol.upper() in symbols

    def get_company_name(self, symbol: str, exchange: str = "NSE") -> Optional[str]:
        """Get company name for a symbol."""
        symbols = NSE_SYMBOLS if exchange.upper() == "NSE" else BSE_SYMBOLS
        return symbols.get(symbol.upper())
