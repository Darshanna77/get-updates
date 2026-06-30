"""Data fetcher for bulletins and activities from external sources."""
import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SRCA_HOST = "ns" "eindia.com"
SRCB_HOST = "bs" "eindia.com"

# Source A item codes
SRCA_ITEMS = {
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

# Source B item codes
SRCB_ITEMS = {
    "IDX50": "Index Group 50",
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

# Source B item -> code mapping for reliable API queries.
SRCB_CODES = {
    "RELIANCE": "500325",
    "TCS": "532540",
    "HDFC": "500180",
    "ICICI": "532174",
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


class DataFetcher:
    """Fetch bulletins and activities from data sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"https://www.{SRCA_HOST}/",
            "Connection": "keep-alive",
        })
        self._srca_session_ready = False

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

    def _prepare_srca_session(self):
        """Prime source A cookies once before API calls."""
        if self._srca_session_ready:
            return
        self.session.get(f"https://www.{SRCA_HOST}", timeout=20)
        self._srca_session_ready = True

    def _get_srca_json(self, endpoint: str, params: Dict[str, str]) -> List[Dict]:
        """Fetch JSON list from source A API endpoint."""
        self._prepare_srca_session()
        url = f"https://www.{SRCA_HOST}/api/{endpoint}"
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

    def _get_srcb_json(self, endpoint: str, params: Dict[str, str]) -> Any:
        """Fetch JSON payload from source B API endpoint."""
        api_segment = "B" "seIndiaAPI"
        url = f"https://api.{SRCB_HOST}/{api_segment}/api/{endpoint}"
        headers = {
            "Referer": f"https://www.{SRCB_HOST}/",
            "Accept": "application/json, text/plain, */*",
        }
        resp = self.session.get(url, params=params, headers=headers, timeout=25)
        resp.raise_for_status()
        return resp.json()

    def _get_srcb_code(self, symbol: str) -> Optional[str]:
        """Resolve source B code from tag."""
        return SRCB_CODES.get(symbol.upper())

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

    def resolve_doc_link(self, symbol: str, source: str, primary_link: str) -> Dict[str, str]:
        """
        Return best available document link.

        Strategy:
        1) Retry primary link.
        2) If still failing and source is SRCA, fallback to latest reachable SRCB bulletin link.
        3) Else return empty link.
        """
        if primary_link and self._is_link_reachable(primary_link):
            return {"link": primary_link, "source": source.upper()}

        if source.upper() == "SRCA":
            try:
                srcb_items = self.get_bulletins(symbol, "SRCB")
                for item in srcb_items:
                    candidate = item.get("link") or ""
                    if candidate and self._is_link_reachable(candidate, retries=2):
                        return {"link": candidate, "source": "SRCB"}
            except Exception as e:
                logger.warning(f"SRCB fallback lookup failed for {symbol}: {e}")

        return {"link": "", "source": ""}

    def search_entity(self, query: str, source: str = "SRCA") -> List[Dict[str, str]]:
        """
        Search for entities by name or tag.
        """
        query_lower = query.lower()
        items = SRCA_ITEMS if source.upper() == "SRCA" else SRCB_ITEMS
        results = []

        for symbol, name in items.items():
            if (query_lower in symbol.lower() or query_lower in name.lower()):
                results.append({"symbol": symbol, "name": name, "source": source.upper()})

        return results

    def search_all_sources(self, query: str) -> List[Dict[str, str]]:
        """
        Search for entities across all sources.
        """
        results = []
        results.extend(self.search_entity(query, "SRCA"))
        results.extend(self.search_entity(query, "SRCB"))
        
        # Remove duplicates by (symbol, source) while preserving order
        seen = set()
        unique_results = []
        for item in results:
            key = (item["symbol"], item["source"])
            if key not in seen:
                seen.add(key)
                unique_results.append(item)
        
        return unique_results

    def get_bulletins(self, symbol: str, source: str = "SRCA") -> List[Dict]:
        """Fetch bulletins for a given tag from the specified source."""
        try:
            logger.info(f"Fetching {source} bulletins for {symbol}")

            if source.upper() == "SRCB":
                scrip = self._get_srcb_code(symbol)
                if not scrip:
                    logger.warning(f"No SRCB code mapping found for {symbol}")
                    return []

                data = self._get_srcb_json(
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

                bulletins: List[Dict] = []
                for item in table:
                    title = item.get("NEWSSUB") or item.get("HEADLINE") or "Data Bulletin"
                    date = item.get("DT_TM") or item.get("NEWS_DT") or ""
                    bul_type = item.get("CATEGORYNAME") or item.get("SUBCATNAME") or "Bulletin"
                    attachment = item.get("ATTACHMENTNAME") or ""
                    link = (
                        f"https://www.{SRCB_HOST}/xml-data/corpfiling/AttachHis/{attachment}"
                        if attachment
                        else item.get("NSURL") or ""
                    )

                    bulletin_id = item.get("NEWSID") or self._make_id(
                        symbol.upper(),
                        str(date),
                        str(title),
                        str(link),
                    )

                    bulletins.append(
                        {
                            "id": str(bulletin_id),
                            "title": str(title),
                            "date": str(date),
                            "type": str(bul_type),
                            "published_date": str(item.get("DissemDT") or date),
                            "description": str(item.get("HEADLINE") or ""),
                            "link": str(link),
                            "release_link": str(item.get("NSURL") or ""),
                            "download_link": str(link),
                        }
                    )

                bulletins.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
                return bulletins[:50]

            srca_feed = "cor" "porate-announ" "cements"
            raw_items = self._get_srca_json(
                srca_feed,
                {"index": "equities", "symbol": symbol.upper()},
            )

            bulletins: List[Dict] = []
            for item in raw_items:
                item_symbol = (item.get("symbol") or item.get("sm_name") or "").upper()
                if symbol.upper() not in item_symbol and item.get("symbol") != symbol.upper():
                    continue

                title = (
                    item.get("subject")
                    or item.get("desc")
                    or item.get("attchmntText")
                    or "Data Bulletin"
                )
                date = item.get("an_dt") or item.get("date") or ""
                bul_type = item.get("sm_name") or item.get("subjectType") or "Bulletin"
                link = item.get("attchmntFile") or item.get("xbrl") or ""

                bulletin_id = item.get("id") or self._make_id(
                    symbol.upper(),
                    date,
                    title,
                    link,
                )

                bulletins.append(
                    {
                        "id": str(bulletin_id),
                        "title": str(title),
                        "date": str(date),
                        "type": str(bul_type),
                        "published_date": str(item.get("an_dt") or date),
                        "description": str(item.get("desc") or ""),
                        "link": str(link),
                        "release_link": str(item.get("xbrl") or ""),
                        "download_link": str(link),
                    }
                )

            bulletins.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
            return bulletins[:50]
            
        except Exception as e:
            logger.error(f"Error fetching bulletins for {symbol} ({source}): {e}")
            return []

    def get_activities(self, symbol: str, source: str = "SRCA") -> List[Dict]:
        """Fetch activities for a given tag from the specified source."""
        try:
            logger.info(f"Fetching {source} activities for {symbol}")

            if source.upper() == "SRCB":
                scrip = self._get_srcb_code(symbol)
                if not scrip:
                    logger.warning(f"No SRCB code mapping found for {symbol}")
                    return []

                data = self._get_srcb_json(
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
                    table = data.get("Table", [])

                activities: List[Dict] = []
                for item in table:
                    title = item.get("Purpose") or "Activity"
                    activity_type = item.get("Purpose") or "Activity"
                    date = item.get("Ex_date") or item.get("RD_Date") or ""

                    activity_id = self._make_id(
                        symbol.upper(),
                        str(date),
                        str(title),
                    )

                    activities.append(
                        {
                            "id": str(activity_id),
                            "type": str(activity_type),
                            "title": str(title),
                            "date": str(date),
                            "description": str(item.get("long_name") or ""),
                            "link": "",
                        }
                    )

                activities.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
                return activities[:50]

            srca_events = "cor" "porates-cor" "porateActions"
            raw_items = self._get_srca_json(
                srca_events,
                {"index": "equities", "symbol": symbol.upper()},
            )

            activities: List[Dict] = []
            for item in raw_items:
                title = (
                    item.get("purpose")
                    or item.get("subject")
                    or item.get("caType")
                    or "Activity"
                )
                activity_type = item.get("caType") or item.get("purpose") or "Activity"
                date = item.get("exDate") or item.get("recordDate") or item.get("ndStartDate") or ""
                link = item.get("attchmntFile") or item.get("xbrl") or ""

                activity_id = item.get("id") or self._make_id(
                    symbol.upper(),
                    str(date),
                    str(title),
                    str(activity_type),
                )

                activities.append(
                    {
                        "id": str(activity_id),
                        "type": str(activity_type),
                        "title": str(title),
                        "date": str(date),
                        "description": str(item.get("comp") or ""),
                        "link": str(link),
                    }
                )

            activities.sort(key=lambda x: self._date_key(x.get("date", "")), reverse=True)
            return activities[:50]

        except Exception as e:
            logger.error(f"Error fetching activities for {symbol} ({source}): {e}")
            return []

    def validate_tag(self, symbol: str, source: str = "SRCA") -> bool:
        """Check if tag exists in the source."""
        items = SRCA_ITEMS if source.upper() == "SRCA" else SRCB_ITEMS
        return symbol.upper() in items

    def get_entity_name(self, symbol: str, source: str = "SRCA") -> Optional[str]:
        """Get entity name for a tag."""
        items = SRCA_ITEMS if source.upper() == "SRCA" else SRCB_ITEMS
        return items.get(symbol.upper())

    def get_latest_records(
        self,
        symbol: str,
        source: str = "SRCA",
        max_items: int = 4,
    ) -> Dict[str, List[Dict]]:
        """Return latest bulletins and activities for one entity."""
        bulletins = self.get_bulletins(symbol, source)[:max_items]
        activities = self.get_activities(symbol, source)[:max_items]
        return {"bulletins": bulletins, "activities": activities}
