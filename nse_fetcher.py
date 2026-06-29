"""NSE and BSE data fetcher for corporate announcements and actions."""
import hashlib
import logging
from typing import Dict, List, Optional

import requests

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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
            "Connection": "keep-alive",
        })
        self._nse_session_ready = False

    def _make_id(self, *parts: str) -> str:
        """Create a deterministic ID for de-duplication."""
        payload = "|".join(parts)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _prepare_nse_session(self):
        """Prime NSE cookies once before API calls."""
        if self._nse_session_ready:
            return
        self.session.get("https://www.nseindia.com", timeout=20)
        self._nse_session_ready = True

    def _get_nse_json(self, endpoint: str, params: Dict[str, str]) -> List[Dict]:
        """Fetch JSON list from NSE API endpoint."""
        self._prepare_nse_session()
        url = f"https://www.nseindia.com/api/{endpoint}"
        resp = self.session.get(url, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                return data["data"]
            return []
        return []

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

            if exchange.upper() != "NSE":
                # BSE endpoint mapping is not stable for symbol-only queries.
                # Keep empty for now to avoid false/misleading alerts.
                return []

            raw_items = self._get_nse_json(
                "corporate-announcements",
                {"index": "equities", "symbol": symbol.upper()},
            )

            announcements: List[Dict] = []
            for item in raw_items:
                item_symbol = (item.get("symbol") or item.get("sm_name") or "").upper()
                if symbol.upper() not in item_symbol and item.get("symbol") != symbol.upper():
                    continue

                title = (
                    item.get("subject")
                    or item.get("desc")
                    or item.get("attchmntText")
                    or "Corporate Announcement"
                )
                date = item.get("an_dt") or item.get("date") or ""
                link = item.get("attchmntFile") or item.get("xbrl") or ""

                announcement_id = item.get("id") or self._make_id(
                    symbol.upper(),
                    date,
                    title,
                    link,
                )

                announcements.append(
                    {
                        "id": str(announcement_id),
                        "title": str(title),
                        "date": str(date),
                        "description": str(item.get("desc") or ""),
                        "link": str(link),
                    }
                )

            # NSE returns long history; cap list to avoid flooding alerts.
            return announcements[:50]
            
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

            if exchange.upper() != "NSE":
                return []

            raw_items = self._get_nse_json(
                "corporates-corporateActions",
                {"index": "equities", "symbol": symbol.upper()},
            )

            actions: List[Dict] = []
            for item in raw_items:
                title = (
                    item.get("purpose")
                    or item.get("subject")
                    or item.get("caType")
                    or "Corporate Action"
                )
                action_type = item.get("caType") or item.get("purpose") or "Action"
                date = item.get("exDate") or item.get("recordDate") or item.get("ndStartDate") or ""
                link = item.get("attchmntFile") or item.get("xbrl") or ""

                action_id = item.get("id") or self._make_id(
                    symbol.upper(),
                    str(date),
                    str(title),
                    str(action_type),
                )

                actions.append(
                    {
                        "id": str(action_id),
                        "type": str(action_type),
                        "title": str(title),
                        "date": str(date),
                        "description": str(item.get("comp") or ""),
                        "link": str(link),
                    }
                )

            # Keep a bounded set for each run to avoid old-history spam.
            return actions[:50]
            
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

    def get_latest_updates(
        self,
        symbol: str,
        exchange: str = "NSE",
        max_items: int = 3,
    ) -> Dict[str, List[Dict]]:
        """Return latest announcements and corporate actions for one company."""
        announcements = self.get_announcements(symbol, exchange)[:max_items]
        actions = self.get_corporate_actions(symbol, exchange)[:max_items]
        return {"announcements": announcements, "actions": actions}
