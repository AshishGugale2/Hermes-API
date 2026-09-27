import logging
import re
from hashlib import sha1
from datetime import date, datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.chittorgarh.com/report/ipo-subscription-status-live-bidding-data-bse-nse/21/"
DATA_API_URL = "https://webnodejs.chittorgarh.com/cloud/report/data-read"
REQUEST_HEADERS = {
    "User-Agent": "IPO-Dashboard/1.0 (+local monitoring; respectful cached requests)",
    "Accept": "text/html,application/xhtml+xml",
}


class SourceFormatError(RuntimeError):
    pass


def fetch_subscriptions() -> List[Dict[str, object]]:
    logger.info("Fetching subscription data from IPO source")
    with httpx.Client(headers=REQUEST_HEADERS, follow_redirects=True, timeout=20.0) as client:
        try:
            records = _fetch_from_data_api(client)
            logger.info("Loaded %d IPO records from data API", len(records))
            return records
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Data API retrieval failed (%s); falling back to HTML parsing", type(exc).__name__)
            response = client.get(SOURCE_URL)
            response.raise_for_status()
            parsed = parse_subscriptions(response.text)
            logger.info("Parsed %d IPO records from source HTML fallback", len(parsed))
            return parsed


def _fetch_from_data_api(client: httpx.Client) -> List[Dict[str, object]]:
    now = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    financial_year_start = now.year if now.month >= 4 else now.year - 1
    endpoint = (
        f"{DATA_API_URL}/21/1/{now.month}/{now.year}/"
        f"{financial_year_start}-{str(financial_year_start + 1)[-2:]}/0/mainboard/$undefined?search="
    )
    logger.debug("Requesting IPO data API endpoint: %s", endpoint)
    response = client.get(endpoint, headers={"Referer": SOURCE_URL})
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("reportTableData", [])
    if payload.get("msg") != 1 or not isinstance(rows, list):
        logger.error("Unexpected data API payload: msg=%s rows_type=%s", payload.get("msg"), type(rows).__name__)
        raise SourceFormatError("The subscription data endpoint returned an unexpected response.")

    records = [_record_from_api_row(row) for row in rows]
    active_records = [record for record in records if record is not None and record["closing_date"] >= now]
    logger.info("Filtered %d valid active IPO records from %d API rows", len(active_records), len(rows))
    return active_records


def _record_from_api_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    company = BeautifulSoup(str(row.get("Company", "")), "html.parser").get_text(" ", strip=True)
    close_date = _parse_date(str(row.get("~Issue_Close_Date", "")))
    if not company or close_date is None:
        logger.debug("Skipping IPO row without company or valid close date: %s", row)
        return None
    record = {
        "id": str(row.get("~id") or _slug(company)),
        "company": re.sub(r"\s+[OP]$", "", company),
        "qib_subscription": _number(row.get("QIB (x)")),
        "nii_subscription": _number(row.get("NII (x)")),
        "retail_subscription": _number(row.get("Retail (x)")),
        "overall_subscription": _number(row.get("Total (x)")),
        "closing_date": close_date,
        "close_date": close_date,
    }
    logger.debug("Parsed IPO record for %s with close date %s", record["company"], close_date.isoformat())
    return record


def _without_closing_date(record: Dict[str, object]) -> Dict[str, object]:
    return {key: value for key, value in record.items() if key != "closing_date"}


def _parse_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _number(value: object) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_subscriptions(html: str) -> List[Dict[str, object]]:
    logger.info("Parsing IPO table from HTML source")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    logger.debug("Inspecting %d HTML tables for IPO data", len(tables))
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [_normalise_header(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
        columns = _find_columns(headers)
        if columns is None:
            continue

        records = _parse_table(rows[1:], columns)
        if records:
            logger.info("Recovered %d IPO records from HTML table parsing", len(records))
            return records

    logger.error("Could not find an IPO subscription table in the HTML source")
    raise SourceFormatError("Could not find an IPO subscription table in the source page.")


def _parse_table(rows, columns: Dict[str, int]) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        if len(cells) <= columns["company"]:
            continue
        values = [cell.get_text(" ", strip=True) for cell in cells]
        company = values[columns["company"]].strip()
        if not company or company.lower() in {"total", "grand total"}:
            continue
        records.append(
            {
                "id": _slug(company),
                "company": company,
                "qib_subscription": _value_at(values, columns.get("qib")),
                "nii_subscription": _value_at(values, columns.get("nii")),
                "retail_subscription": _value_at(values, columns.get("retail")),
                "overall_subscription": _value_at(values, columns.get("overall")),
            }
        )
    return records


def _find_columns(headers: List[str]) -> Optional[Dict[str, int]]:
    company = _first_index(headers, ("ipo", "company", "issue name"))
    retail = _first_index(headers, ("retail", "rii"))
    overall = _first_index(headers, ("overall", "total", "subscription"))
    if company is None or retail is None or overall is None:
        return None
    return {
        "company": company,
        "retail": retail,
        "overall": overall,
        "qib": _first_index(headers, ("qib", "qualified")),
        "nii": _first_index(headers, ("nii", "hni", "non institutional")),
    }


def _normalise_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _first_index(headers: List[str], terms) -> Optional[int]:
    for index, header in enumerate(headers):
        if any(term in header for term in terms):
            return index
    return None


def _value_at(values: List[str], index: Optional[int]) -> Optional[float]:
    if index is None or index >= len(values):
        return None
    value = values[index].replace(",", "")
    match = re.search(r"(?:\d+(?:\.\d+)?)", value)
    return float(match.group()) if match else None


def _slug(value: str) -> str:
    normalised = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{normalised[:56]}-{sha1(value.encode()).hexdigest()[:8]}"
