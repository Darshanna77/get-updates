"""NSE and BSE data fetcher for corporate announcements and actions."""
import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

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

# BSE symbol -> scrip code mapping for reliable API queries.
# These are stable exchange identifiers, independent of website UI.
BSE_SCRIP_CODES = {
    "RELIANCE": "500325",
    "TCS": "532540",
    "HDFC": "500180",   # HDFC Bank
    "ICICI": "532174",  # ICICI Bank
    "INFY": "500209",
    "LT": "500510",
    "ITC": "500875",
    "SBIN": "500112",
    "MARUTI": "532500",
    "TECHM": "532755",
    "WIPRO": "507685",
    "AXIS": "532215",
    "HCL": "532281",
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

    def _date_key(self, value: str) -> datetime:
        """Best-effort date parser for sorting newest first."""
        if not value:
            return datetime.min

        value = str(value).strip()
        fmts = [
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%d %b %Y",
            "%Y%m%d",
        ]
        for fmt in fmts:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return datetime.min

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

    def _get_bse_json(self, endpoint: str, params: Dict[str, str]) -> Any:
        """Fetch JSON payload from BSE API endpoint."""
        url = f"https://api.bseindia.com/BseIndiaAPI/api/{endpoint}"
        headers = {
            "Referer": "https://www.bseindia.com/",
            "Accept": "application/json, text/plain, */*",
        }
        resp = self.session.get(url, params=params, headers=headers, timeout=25)
        resp.raise_for_status()
        return resp.json()

    def _get_bse_scrip_code(self, symbol: str) -> Optional[str]:
        """Resolve BSE scrip code from symbol."""
        return BSE_SCRIP_CODES.get(symbol.upper())

    def _is_link_reachable(self, url: str, retries: int = 3) -> bool:
        """Check if a document URL is reachable with lightweight retries."""
        if not url:
            return False

        for attempt in range(retries):
            try:
                # Some hosts reject HEAD, so try GET stream first.
                resp = self.session.get(url, timeout=12, allow_redirects=True, stream=True)
                if 200 <= resp.status_code < 300:
                    return True
            except Exception:
                pass

            # Small backoff for transient CDN/network errors.
            time.sleep(0.8 * (attempt + 1))

        return False

    def resolve_statement_link(self, symbol: str, exchange: str, primary_link: str) -> Dict[str, str]:
        """
        Return best available statement link.

        Strategy:
        1) Retry primary link.
        2) If still failing and exchange is NSE, fallback to latest reachable BSE announcement link.
        3) Else return empty link.
        """
        if primary_link and self._is_link_reachable(primary_link):
            return {"link": primary_link, "source": exchange.upper()}

        if exchange.upper() == "NSE":
            try:
                bse_items = self.get_announcements(symbol, "BSE")
                for item in bse_items:
                    candidate = item.get("link") or ""
                    if candidate and self._is_link_reachable(candidate, retries=2):
                        return {"link": candidate, "source": "BSE"}
            except Exception as e:
                logger.warning(f"BSE fallback lookup failed for {symbol}: {e}")

        return {"link": "", "source": ""}

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

            if exchange.upper() == "BSE":
                scrip = self._get_bse_scrip_code(symbol)
                if not scrip:
                    logger.warning(f"No BSE scrip code mapping found for {symbol}")
                    return []

                data = self._get_bse_json(
                    "AnnSubCategoryGetData/w",
                    {
                        "pageno": "1",
                        "strCat": "-1",
                        "strPrevDate": "20200101",
                        "strScrip": scrip,
                        "strSearch": "S",
                        "strToDate": "20991231",
                        "strType": "C",
                        "subcategory": "-1",
                    },
                )
                table = data.get("Table", []) if isinstance(data, dict) else []

                announcements: List[Dict] = []
                for item in table:
                    title = item.get("NEWSSUB") or item.get("HEADLINE") or "Corporate Announcement"
                    date = item.get("DT_TM") or item.get("NEWS_DT") or ""
                    attachment = item.get("ATTACHMENTNAME") or ""
                    link = (
                        f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{attachment}"
                        if attachment
                        else item.get("NSURL") or ""
                    )

                    announcement_id = item.get("NEWSID") or self._make_id(
                        symbol.upper(),
                        str(date),
                        str(title),
                        str(link),
                    )

                    announcements.append(
                        {
                            "id": str(announcement_id),
                            "title": str(title),
                            "date": str(date),
                            "description": str(item.get("HEADLINE") or ""),
                            "link": str(link),
                        }
                    )

                announcements.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
                return announcements[:50]

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

            announcements.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
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

            if exchange.upper() == "BSE":
                scrip = self._get_bse_scrip_code(symbol)
                if not scrip:
                    logger.warning(f"No BSE scrip code mapping found for {symbol}")
                    return []

                data = self._get_bse_json(
                    "DefaultData/w",
                    {
                        "scripcode": scrip,
                        "Fdate": "",
                        "Purposecode": "",
                        "TDate": "",
                        "ddlcategorys": "E",
                        "ddlindustrys": "",
                        "segment": "0",
                        "strSearch": "D",
                    },
                )
                table = data if isinstance(data, list) else []
                if isinstance(data, dict):
                    # Some responses can be wrapped in a "Table" key depending on deployment.
                    table = data.get("Table", [])

                actions: List[Dict] = []
                for item in table:
                    title = item.get("Purpose") or "Corporate Action"
                    action_type = item.get("Purpose") or "Action"
                    date = item.get("Ex_date") or item.get("RD_Date") or ""

                    action_id = self._make_id(
                        symbol.upper(),
                        str(date),
                        str(title),
                    )

                    actions.append(
                        {
                            "id": str(action_id),
                            "type": str(action_type),
                            "title": str(title),
                            "date": str(date),
                            "description": str(item.get("long_name") or ""),
                            "link": "",
                        }
                    )

                actions.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
                return actions[:50]

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

            actions.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
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
        max_items: int = 4,
    ) -> Dict[str, List[Dict]]:
        """Return latest announcements and corporate actions for one company."""
        announcements = self.get_announcements(symbol, exchange)[:max_items]
        actions = self.get_corporate_actions(symbol, exchange)[:max_items]
        return {"announcements": announcements, "actions": actions}
