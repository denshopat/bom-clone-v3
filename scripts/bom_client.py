"""BOM client — single network-edge module for bom.gov.au.

Owns: HTTP headers, timeouts, URL construction, response validation,
filename conventions for downloaded artifacts.

Does NOT own: retries, courtesy sleeps between requests, on-disk caching,
"skip if file already present" logic, atomic writes — those belong in the
orchestration layer (planners and the Download log).

See CONTEXT.md for the vocabulary used here (Station, Station list,
Station metadata PDF, Observation zip, Product).
"""
from __future__ import annotations

import html as _html
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Literal

ListName = Literal["alphaAUS_3", "numAUS_139"]
Product = Literal["rainfall", "max_temp", "min_temp"]

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/115.0"
_DEFAULT_TIMEOUT = 30

_LIST_URL = "https://www.bom.gov.au/climate/data/lists_by_element/{name}.txt"
_METADATA_URL = (
    "https://www.bom.gov.au/clim_data/cdio/metadata/pdf/siteinfo/{filename}"
)
_DATAFILE_URL = "https://www.bom.gov.au/jsp/ncc/cdio/weatherData/av"

_OBS_CODES: dict[Product, str] = {
    "rainfall": "136",
    "max_temp": "122",
    "min_temp": "123",
}

_PRODUCT_PREFIX: dict[Product, str] = {
    "rainfall": "IDCJAC0009",
    "max_temp": "IDCJAC0010",
    "min_temp": "IDCJAC0011",
}


class BomFetchError(Exception):
    """Base for all BOM client errors. Wraps network errors too."""


class BomValidationError(BomFetchError):
    """Response was fetched but failed validation (wrong content-type,
    blocked page, malformed body). The bad bytes are attached for logging."""

    def __init__(self, message: str, body: bytes = b"") -> None:
        super().__init__(message)
        self.body = body


class BomNotFoundError(BomFetchError):
    """The expected payload isn't present at the URL — currently used when
    a dataFile landing page has no 'All years of data' link."""


def obs_code_for(product: Product) -> str:
    """BOM observation code for a product. Exposed because the resume-CSV
    log files store the obs code as a column."""
    return _OBS_CODES[product]


def metadata_pdf_filename(station_number: int) -> str:
    return f"IDCJMD0040.{station_number:06d}.SiteInfo.pdf"


def observation_zip_filename(station_number: int, product: Product) -> str:
    return f"{_PRODUCT_PREFIX[product]}_{station_number}_1800.zip"


def product_from_zip_filename(filename: str) -> Product | None:
    """Inverse of observation_zip_filename. Returns None if the filename
    doesn't match the BOM convention."""
    parts = filename.split("_")
    if len(parts) < 3:
        return None
    prefix = parts[0]
    for product, expected_prefix in _PRODUCT_PREFIX.items():
        if expected_prefix == prefix:
            return product
    return None


def _http_get(
    url: str,
    *,
    accept: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> tuple[bytes, str]:
    """Single private transport. Tests monkeypatch this to stub the network."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read()
            content_type = resp.info().get("Content-Type", "") or ""
    except (urllib.error.URLError, TimeoutError) as exc:
        raise BomFetchError(f"GET {url} failed: {exc}") from exc
    return body, content_type


def fetch_station_list(name: ListName) -> bytes:
    url = _LIST_URL.format(name=name)
    body, _ = _http_get(url, accept="text/plain,text/html")
    text = body.decode("utf-8", errors="ignore")
    if "Bureau of Meteorology product" not in text:
        raise BomValidationError(f"{name}: missing BOM product header", body)
    if "Your access is blocked" in text or (
        "lists_by_element" in text and "access is blocked" in text.lower()
    ):
        raise BomValidationError(f"{name}: access blocked", body)
    if "Site    Name" not in text or "-" * 10 not in text:
        raise BomValidationError(f"{name}: list body malformed", body)
    return body


def fetch_metadata_pdf(station_number: int) -> bytes:
    filename = metadata_pdf_filename(station_number)
    url = _METADATA_URL.format(filename=filename)
    body, content_type = _http_get(url, accept="application/pdf,text/html")
    if "application/pdf" not in content_type.lower() and not body.startswith(b"%PDF"):
        raise BomValidationError(
            f"station {station_number}: response is not a PDF", body
        )
    return body


def _scrape_all_years_link(html_text: str) -> str | None:
    patterns = [
        r'href="([^"]+)"[^>]*>All years of data',
        r'href="([^"]+)"[^>]*>All Years of Data',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            link = _html.unescape(match.group(1))
            if link.startswith("/"):
                link = urllib.parse.urljoin("https://www.bom.gov.au", link)
            return link
    return None


def fetch_observation_zip(station_number: int, product: Product) -> bytes:
    obs_code = _OBS_CODES[product]
    params = {
        "p_nccObsCode": obs_code,
        "p_display_type": "dailyDataFile",
        "p_stn_num": str(station_number),
    }
    landing_url = f"{_DATAFILE_URL}?{urllib.parse.urlencode(params)}"
    landing_body, _ = _http_get(
        landing_url, accept="text/html,application/xhtml+xml"
    )
    landing_text = landing_body.decode("utf-8", errors="ignore")
    zip_url = _scrape_all_years_link(landing_text)
    if not zip_url:
        raise BomNotFoundError(
            f"station {station_number} {product}: no 'All years of data' link"
        )
    zip_body, content_type = _http_get(
        zip_url, accept="application/zip,application/octet-stream"
    )
    if "text/html" in content_type.lower():
        raise BomValidationError(
            f"station {station_number} {product}: got HTML when expecting zip",
            zip_body,
        )
    return zip_body
