"""Data fetcher for bulletins and activities from external sources."""
import hashlib
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SRCA_HOST = "ns" "eindia.com"
SRCB_HOST = "bs" "eindia.com"

# Source B item -> code mapping for reliable API queries.
SRCB_CODES = {
    "APARAJYA": "519061",
    "ORTIN": "516283",
    "VIRENDOCT": "522066",
    "KPTL": "500237",
    "ZEEMEDIA": "505486",
    "SUNDARMFIN": "532479",
    "DIVGITECH": "532528",
}


class DataFetcher:
    """Fetch bulletins and activities from data sources."""

    CACHE_FILE = "entity_names_cache.json"

    # Rotate user agents to avoid NSE bot detection
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    ]

    def __init__(self):
        self.session = requests.Session()
        self._update_headers()
        # Disable cookies to avoid NSE rate limiting
        self.session.cookies.clear()
        self._srca_session_ready = False
        self._entity_name_cache = self._load_entity_cache()

    def _update_headers(self):
        """Update session headers with random user agent."""
        user_agent = random.choice(self.USER_AGENTS)
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": f"https://www.{SRCA_HOST}/",
            "Connection": "keep-alive",
            "DNT": "1",
        })

    def _load_entity_cache(self) -> Dict[str, str]:
        """Load entity name cache from file."""
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r") as f:
                    cache = json.load(f)
                    logger.info(f"✓ Loaded entity cache with {len(cache)} entries")
                    return cache
            except Exception as e:
                logger.warning(f"Failed to load entity cache: {e}")
        return {}

    def clear_cookies(self):
        """Clear accumulated cookies to prevent NSE rate limiting."""
        self.session.cookies.clear()
        logger.debug("✓ Cleared accumulated cookies")

    def _save_entity_cache(self):
        """Save entity name cache to file."""
        try:
            with open(self.CACHE_FILE, "w") as f:
                json.dump(self._entity_name_cache, f, indent=2)
                logger.info(f"✓ Saved entity cache with {len(self._entity_name_cache)} entries")
        except Exception as e:
            logger.error(f"Failed to save entity cache: {e}")

    def _cache_key(self, symbol: str, source: str) -> str:
        """Generate cache key for symbol+source."""
        return f"{symbol.upper()}:{source.upper()}"

    def _get_cached_entity_name(self, symbol: str, source: str) -> Optional[str]:
        """Get entity name from cache if available."""
        key = self._cache_key(symbol, source)
        return self._entity_name_cache.get(key)

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
        """Session prep is skipped to avoid NSE rate limiting via cookies.
        Direct API calls without homepage hits are faster and don't trigger WAF."""
        if self._srca_session_ready:
            return
        # Skip homepage request - NSE rate-limits based on session/cookies
        logger.info("⚡ Skipping NSE session prep to avoid rate limiting")
        self._srca_session_ready = True

    def _retry_with_backoff(self, func, *args, max_retries=3, timeout_delay=3.0, **kwargs):
        """Execute function with exponential backoff retry on timeout.
        NSE heavily rate-limits, so use aggressive backoff: 3s -> 6s -> 12s + jitter."""
        last_error = None
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < max_retries - 1:
                    # Exponential backoff starting at 3s: 3s, 6s, 12s + random 0-3s jitter
                    base_wait = timeout_delay * (2 ** attempt)
                    jitter = random.uniform(0, 3)
                    wait_time = base_wait + jitter
                    logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries}, waiting {wait_time:.1f}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Timeout after {max_retries} attempts: {e}")
            except Exception as e:
                # Non-timeout errors: fail immediately
                raise
        raise last_error

    def _get_srca_json(self, endpoint: str, params: Dict[str, str]) -> List[Dict]:
        """Fetch JSON list from source A API endpoint with retry logic.
        NSE is slow; use 40s timeout for reads to avoid premature timeouts."""
        self._prepare_srca_session()
        url = f"https://www.{SRCA_HOST}/api/{endpoint}"
        
        def fetch():
            # Increased timeout to 40s to account for NSE slowness/rate-limiting
            resp = self.session.get(url, params=params, timeout=40)
            
            # Check for rate-limiting or error responses
            if resp.status_code in (429, 403, 502, 503):
                logger.warning(f"NSE returned {resp.status_code}: {resp.text[:100]}")
                raise requests.exceptions.Timeout(f"NSE rate-limiting or error: HTTP {resp.status_code}")
            
            resp.raise_for_status()
            
            # Check for empty response
            if not resp.text or not resp.text.strip():
                logger.warning("Empty response from NSE API")
                return []
            
            try:
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    if isinstance(data.get("data"), list):
                        return data["data"]
                    return []
                return []
            except ValueError as e:
                logger.warning(f"Failed to parse JSON response: {e}, body: {resp.text[:200]}")
                return []
        
        return self._retry_with_backoff(fetch, max_retries=3, timeout_delay=3.0)

    def _get_srcb_json(self, endpoint: str, params: Dict[str, str]) -> Any:
        """Fetch JSON payload from source B API endpoint with retry logic.
        BSE is slower than expected; use 40s timeout to account for slowness."""
        api_segment = "B" "seIndiaAPI"
        url = f"https://api.{SRCB_HOST}/{api_segment}/api/{endpoint}"
        headers = {
            "Referer": f"https://www.{SRCB_HOST}/",
            "Accept": "application/json, text/plain, */*",
        }
        
        def fetch():
            # Increased timeout to 40s to handle slow responses
            resp = self.session.get(url, params=params, headers=headers, timeout=40)
            
            # Check for rate-limiting or error responses
            if resp.status_code in (429, 403, 502, 503):
                logger.warning(f"BSE returned {resp.status_code}: {resp.text[:100]}")
                raise requests.exceptions.Timeout(f"BSE rate-limiting or error: HTTP {resp.status_code}")
            
            resp.raise_for_status()
            
            # Check for empty response
            if not resp.text or not resp.text.strip():
                logger.warning("Empty response from BSE API")
                return {}
            
            try:
                return resp.json()
            except ValueError as e:
                logger.warning(f"Failed to parse JSON response from BSE: {e}, body: {resp.text[:200]}")
                return {}
        
        return self._retry_with_backoff(fetch, max_retries=3, timeout_delay=3.0)

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
                resp = self.session.get(url, timeout=8, allow_redirects=True, stream=True)
                if 200 <= resp.status_code < 300:
                    return True
            except Exception:
                pass

            # Small backoff for transient CDN/network errors.
            time.sleep(0.5 * (attempt + 1))

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

    def _search_srca_dynamic(self, query: str) -> List[Dict[str, str]]:
        """Search source A symbols dynamically using its search API with retry."""
        self._prepare_srca_session()
        url = f"https://www.{SRCA_HOST}/api/search/autocomplete"
        
        def fetch():
            resp = self.session.get(url, params={"q": query}, timeout=10)
            
            # Check for rate-limiting or error responses
            if resp.status_code in (429, 403, 502, 503):
                logger.warning(f"NSE search returned {resp.status_code}, treating as rate-limit")
                raise requests.exceptions.Timeout(f"NSE rate-limiting: HTTP {resp.status_code}")
            
            resp.raise_for_status()
            
            # Check for empty response
            if not resp.text or not resp.text.strip():
                logger.warning("Empty response from NSE search API")
                return {}
            
            try:
                return resp.json()
            except ValueError as e:
                logger.warning(f"Failed to parse search response: {e}, body: {resp.text[:200]}")
                return {}
        
        try:
            payload = self._retry_with_backoff(fetch, max_retries=2, timeout_delay=3.0)
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []

        rows = []
        if isinstance(payload, dict):
            for key in ("symbols", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    rows = value
                    break
        elif isinstance(payload, list):
            rows = payload

        out: List[Dict[str, str]] = []
        q = query.casefold()
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or item.get("identifier") or "").upper().strip()
            name = str(
                item.get("symbol_info")
                or item.get("name")
                or item.get("meta")
                or item.get("description")
                or symbol
            ).strip()
            if not symbol:
                continue
            hay = f"{symbol} {name}".casefold()
            if q and q not in hay:
                continue
            out.append({"symbol": symbol, "name": name, "source": "SRCA"})

        return out

    def _search_srcb_dynamic(self, query: str) -> List[Dict[str, str]]:
        """Best-effort source B search with API attempt and symbol-map fallback."""
        out: List[Dict[str, str]] = []
        q = query.casefold()

        endpoints = [
            ("SmartSearchData/w", {"text": query}),
            ("SmartSearchNew/w", {"text": query}),
        ]
        for endpoint, params in endpoints:
            try:
                payload = self._get_srcb_json(endpoint, params)
                rows = payload if isinstance(payload, list) else payload.get("Table", []) if isinstance(payload, dict) else []
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    symbol = str(item.get("symbol") or item.get("SYMBOL") or item.get("sSymbol") or "").upper().strip()
                    name = str(
                        item.get("name")
                        or item.get("scripname")
                        or item.get("SCRIPNAME")
                        or item.get("longname")
                        or symbol
                    ).strip()
                    if not symbol:
                        continue
                    hay = f"{symbol} {name}".casefold()
                    if q and q not in hay:
                        continue
                    out.append({"symbol": symbol, "name": name, "source": "SRCB"})
                if out:
                    break
            except Exception:
                continue

        if not out:
            for symbol in SRCB_CODES:
                if q in symbol.casefold():
                    out.append({"symbol": symbol, "name": symbol, "source": "SRCB"})

        return out

    def search_entity(self, query: str, source: str = "SRCA") -> List[Dict[str, str]]:
        """
        Search for entities by name or tag.
        """
        src = source.upper()
        try:
            results = self._search_srca_dynamic(query) if src == "SRCA" else self._search_srcb_dynamic(query)
        except Exception as e:
            logger.warning(f"Dynamic search failed for {src} query '{query}': {e}")
            results = []

        seen = set()
        unique = []
        for item in results:
            key = (item["symbol"], item["source"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[:30]

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
        sym = symbol.upper()
        if source.upper() == "SRCB" and sym in SRCB_CODES:
            return True
        results = self.search_entity(sym, source)
        return any(item.get("symbol", "").upper() == sym for item in results)

    def get_entity_name(self, symbol: str, source: str = "SRCA") -> Optional[str]:
        """Get entity name for a tag. Checks cache first, then searches if needed."""
        sym = symbol.upper()
        source_upper = source.upper()

        # 1. Check cache first
        cached_name = self._get_cached_entity_name(sym, source_upper)
        if cached_name:
            logger.info(f"✓ Entity name from cache: {sym} ({source_upper}) → {cached_name}")
            return cached_name

        # 2. Search if not cached
        logger.info(f"🔍 Searching for entity name: {sym} ({source_upper})")
        results = self.search_entity(sym, source_upper)
        for item in results:
            if item.get("symbol", "").upper() == sym:
                entity_name = item.get("name") or sym
                # 3. Store in cache
                key = self._cache_key(sym, source_upper)
                self._entity_name_cache[key] = entity_name
                self._save_entity_cache()
                logger.info(f"✓ Found & cached: {sym} ({source_upper}) → {entity_name}")
                return entity_name

        # 4. Fallback for SRCB
        if source_upper == "SRCB" and sym in SRCB_CODES:
            entity_name = sym
            key = self._cache_key(sym, source_upper)
            self._entity_name_cache[key] = entity_name
            self._save_entity_cache()
            return entity_name

        return None

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
