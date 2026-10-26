"""
Real Exchange Rate Explorer
===========================

Streamlit app that downloads monthly IMF CPI and exchange-rate data (SDMX 3.0 API)
for two economies and computes the bilateral nominal and real exchange rate.

Conventions used throughout the app
-----------------------------------
S(t)   = units of Country 2's currency per ONE unit of Country 1's currency
       = (Country 2 LCU per USD) / (Country 1 LCU per USD)
P1, P2 = monthly consumer price indices of Country 1 and Country 2
RER(t) = S(t) * P1(t) / P2(t)
RER*   = mean of RER(t) over valid months in the selected sample
Real Index(t) = 100 * RER(t) / RER*

A rise in S(t) or in the Real Index means Country 1's currency strengthens
(nominal / real appreciation of Country 1 against Country 2).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IMF_BASE_URL = "https://api.imf.org/external/sdmx/3.0"
IMF_AGENCY = "IMF.STA"
CPI_DATAFLOW = "CPI"
ER_DATAFLOW = "ER"
CPI_KEY_TEMPLATE = "{iso3}.CPI._T.IX.M"  # CPI, all items, index, monthly
ER_KEY_TEMPLATE = "{iso3}.XDC_USD.PA_RT.M"  # domestic currency per USD, period average, monthly
DATA_START = pd.Period("1976-01", freq="M")
EURO_AREA_CODE = "G163"
REQUEST_TIMEOUT = 60
CACHE_TTL_SECONDS = 24 * 60 * 60
LARGE_MOVE_THRESHOLD = 0.30  # flag one-month nominal moves larger than 30 %

# Colors (validated categorical slots 1 and 2 of the reference data-viz palette)
COLOR_REAL = "#2a78d6"
COLOR_NOMINAL = "#eb6834"
COLOR_REFERENCE = "#8a8984"

# ISO3 code -> (display name, current ISO 4217 currency code).
# IMF member countries plus selected territories reported by the IMF, and the Euro area.
COUNTRIES: dict[str, tuple[str, str]] = {
    EURO_AREA_CODE: ("Euro area", "EUR"),
    "AFG": ("Afghanistan", "AFN"),
    "ALB": ("Albania", "ALL"),
    "DZA": ("Algeria", "DZD"),
    "AND": ("Andorra", "EUR"),
    "AGO": ("Angola", "AOA"),
    "AIA": ("Anguilla", "XCD"),
    "ATG": ("Antigua and Barbuda", "XCD"),
    "ARG": ("Argentina", "ARS"),
    "ARM": ("Armenia", "AMD"),
    "ABW": ("Aruba", "AWG"),
    "AUS": ("Australia", "AUD"),
    "AUT": ("Austria", "EUR"),
    "AZE": ("Azerbaijan", "AZN"),
    "BHS": ("Bahamas", "BSD"),
    "BHR": ("Bahrain", "BHD"),
    "BGD": ("Bangladesh", "BDT"),
    "BRB": ("Barbados", "BBD"),
    "BLR": ("Belarus", "BYN"),
    "BEL": ("Belgium", "EUR"),
    "BLZ": ("Belize", "BZD"),
    "BEN": ("Benin", "XOF"),
    "BTN": ("Bhutan", "BTN"),
    "BOL": ("Bolivia", "BOB"),
    "BIH": ("Bosnia and Herzegovina", "BAM"),
    "BWA": ("Botswana", "BWP"),
    "BRA": ("Brazil", "BRL"),
    "BRN": ("Brunei Darussalam", "BND"),
    "BGR": ("Bulgaria", "EUR"),
    "BFA": ("Burkina Faso", "XOF"),
    "BDI": ("Burundi", "BIF"),
    "CPV": ("Cabo Verde", "CVE"),
    "KHM": ("Cambodia", "KHR"),
    "CMR": ("Cameroon", "XAF"),
    "CAN": ("Canada", "CAD"),
    "CAF": ("Central African Republic", "XAF"),
    "TCD": ("Chad", "XAF"),
    "CHL": ("Chile", "CLP"),
    "CHN": ("China", "CNY"),
    "COL": ("Colombia", "COP"),
    "COM": ("Comoros", "KMF"),
    "COD": ("Congo, Democratic Republic of the", "CDF"),
    "COG": ("Congo, Republic of", "XAF"),
    "CRI": ("Costa Rica", "CRC"),
    "CIV": ("Côte d'Ivoire", "XOF"),
    "HRV": ("Croatia", "EUR"),
    "CUW": ("Curaçao", "XCG"),
    "CYP": ("Cyprus", "EUR"),
    "CZE": ("Czech Republic", "CZK"),
    "DNK": ("Denmark", "DKK"),
    "DJI": ("Djibouti", "DJF"),
    "DMA": ("Dominica", "XCD"),
    "DOM": ("Dominican Republic", "DOP"),
    "ECU": ("Ecuador", "USD"),
    "EGY": ("Egypt", "EGP"),
    "SLV": ("El Salvador", "USD"),
    "GNQ": ("Equatorial Guinea", "XAF"),
    "ERI": ("Eritrea", "ERN"),
    "EST": ("Estonia", "EUR"),
    "SWZ": ("Eswatini", "SZL"),
    "ETH": ("Ethiopia", "ETB"),
    "FJI": ("Fiji", "FJD"),
    "FIN": ("Finland", "EUR"),
    "FRA": ("France", "EUR"),
    "GAB": ("Gabon", "XAF"),
    "GMB": ("Gambia", "GMD"),
    "GEO": ("Georgia", "GEL"),
    "DEU": ("Germany", "EUR"),
    "GHA": ("Ghana", "GHS"),
    "GRC": ("Greece", "EUR"),
    "GRD": ("Grenada", "XCD"),
    "GTM": ("Guatemala", "GTQ"),
    "GIN": ("Guinea", "GNF"),
    "GNB": ("Guinea-Bissau", "XOF"),
    "GUY": ("Guyana", "GYD"),
    "HTI": ("Haiti", "HTG"),
    "HND": ("Honduras", "HNL"),
    "HKG": ("Hong Kong SAR, China", "HKD"),
    "HUN": ("Hungary", "HUF"),
    "ISL": ("Iceland", "ISK"),
    "IND": ("India", "INR"),
    "IDN": ("Indonesia", "IDR"),
    "IRN": ("Iran", "IRR"),
    "IRQ": ("Iraq", "IQD"),
    "IRL": ("Ireland", "EUR"),
    "ISR": ("Israel", "ILS"),
    "ITA": ("Italy", "EUR"),
    "JAM": ("Jamaica", "JMD"),
    "JPN": ("Japan", "JPY"),
    "JOR": ("Jordan", "JOD"),
    "KAZ": ("Kazakhstan", "KZT"),
    "KEN": ("Kenya", "KES"),
    "KIR": ("Kiribati", "AUD"),
    "KOR": ("Korea, Republic of", "KRW"),
    "XKX": ("Kosovo", "EUR"),
    "KWT": ("Kuwait", "KWD"),
    "KGZ": ("Kyrgyz Republic", "KGS"),
    "LAO": ("Lao P.D.R.", "LAK"),
    "LVA": ("Latvia", "EUR"),
    "LBN": ("Lebanon", "LBP"),
    "LSO": ("Lesotho", "LSL"),
    "LBR": ("Liberia", "LRD"),
    "LBY": ("Libya", "LYD"),
    "LIE": ("Liechtenstein", "CHF"),
    "LTU": ("Lithuania", "EUR"),
    "LUX": ("Luxembourg", "EUR"),
    "MAC": ("Macao SAR, China", "MOP"),
    "MDG": ("Madagascar", "MGA"),
    "MWI": ("Malawi", "MWK"),
    "MYS": ("Malaysia", "MYR"),
    "MDV": ("Maldives", "MVR"),
    "MLI": ("Mali", "XOF"),
    "MLT": ("Malta", "EUR"),
    "MHL": ("Marshall Islands", "USD"),
    "MRT": ("Mauritania", "MRU"),
    "MUS": ("Mauritius", "MUR"),
    "MEX": ("Mexico", "MXN"),
    "FSM": ("Micronesia", "USD"),
    "MDA": ("Moldova", "MDL"),
    "MNG": ("Mongolia", "MNT"),
    "MNE": ("Montenegro", "EUR"),
    "MSR": ("Montserrat", "XCD"),
    "MAR": ("Morocco", "MAD"),
    "MOZ": ("Mozambique", "MZN"),
    "MMR": ("Myanmar", "MMK"),
    "NAM": ("Namibia", "NAD"),
    "NRU": ("Nauru", "AUD"),
    "NPL": ("Nepal", "NPR"),
    "NLD": ("Netherlands", "EUR"),
    "NZL": ("New Zealand", "NZD"),
    "NIC": ("Nicaragua", "NIO"),
    "NER": ("Niger", "XOF"),
    "NGA": ("Nigeria", "NGN"),
    "MKD": ("North Macedonia", "MKD"),
    "NOR": ("Norway", "NOK"),
    "OMN": ("Oman", "OMR"),
    "PAK": ("Pakistan", "PKR"),
    "PLW": ("Palau", "USD"),
    "PAN": ("Panama", "PAB"),
    "PNG": ("Papua New Guinea", "PGK"),
    "PRY": ("Paraguay", "PYG"),
    "PER": ("Peru", "PEN"),
    "PHL": ("Philippines", "PHP"),
    "POL": ("Poland", "PLN"),
    "PRT": ("Portugal", "EUR"),
    "QAT": ("Qatar", "QAR"),
    "ROU": ("Romania", "RON"),
    "RUS": ("Russian Federation", "RUB"),
    "RWA": ("Rwanda", "RWF"),
    "WSM": ("Samoa", "WST"),
    "SMR": ("San Marino", "EUR"),
    "STP": ("São Tomé and Príncipe", "STN"),
    "SAU": ("Saudi Arabia", "SAR"),
    "SEN": ("Senegal", "XOF"),
    "SRB": ("Serbia", "RSD"),
    "SYC": ("Seychelles", "SCR"),
    "SLE": ("Sierra Leone", "SLE"),
    "SGP": ("Singapore", "SGD"),
    "SXM": ("Sint Maarten", "XCG"),
    "SVK": ("Slovak Republic", "EUR"),
    "SVN": ("Slovenia", "EUR"),
    "SLB": ("Solomon Islands", "SBD"),
    "SOM": ("Somalia", "SOS"),
    "ZAF": ("South Africa", "ZAR"),
    "SSD": ("South Sudan", "SSP"),
    "ESP": ("Spain", "EUR"),
    "LKA": ("Sri Lanka", "LKR"),
    "KNA": ("St. Kitts and Nevis", "XCD"),
    "LCA": ("St. Lucia", "XCD"),
    "VCT": ("St. Vincent and the Grenadines", "XCD"),
    "SDN": ("Sudan", "SDG"),
    "SUR": ("Suriname", "SRD"),
    "SWE": ("Sweden", "SEK"),
    "CHE": ("Switzerland", "CHF"),
    "SYR": ("Syrian Arab Republic", "SYP"),
    "TJK": ("Tajikistan", "TJS"),
    "TZA": ("Tanzania", "TZS"),
    "THA": ("Thailand", "THB"),
    "TLS": ("Timor-Leste", "USD"),
    "TGO": ("Togo", "XOF"),
    "TON": ("Tonga", "TOP"),
    "TTO": ("Trinidad and Tobago", "TTD"),
    "TUN": ("Tunisia", "TND"),
    "TUR": ("Türkiye", "TRY"),
    "TKM": ("Turkmenistan", "TMT"),
    "TUV": ("Tuvalu", "AUD"),
    "UGA": ("Uganda", "UGX"),
    "UKR": ("Ukraine", "UAH"),
    "ARE": ("United Arab Emirates", "AED"),
    "GBR": ("United Kingdom", "GBP"),
    "USA": ("United States", "USD"),
    "URY": ("Uruguay", "UYU"),
    "UZB": ("Uzbekistan", "UZS"),
    "VUT": ("Vanuatu", "VUV"),
    "VEN": ("Venezuela", "VES"),
    "VNM": ("Vietnam", "VND"),
    "PSE": ("West Bank and Gaza", "ILS"),
    "YEM": ("Yemen", "YER"),
    "ZMB": ("Zambia", "ZMW"),
    "ZWE": ("Zimbabwe", "ZWG"),
}


class IMFDataError(RuntimeError):
    """Raised when the IMF API cannot be reached or returns unusable content."""


# ---------------------------------------------------------------------------
# IMF SDMX 3.0 client
# ---------------------------------------------------------------------------
_HTTP = requests.Session()
_HTTP.headers.update({"User-Agent": "real-exchange-rate-explorer/1.0 (Streamlit; educational use)"})

# Tried in order until the server returns something we can parse.
_ACCEPT_HEADERS = (
    "application/vnd.sdmx.data+json;version=2.0.0",
    "application/json",
    "application/vnd.sdmx.structurespecificdata+xml;version=3.0.0",
    "application/xml",
)
_DATAFLOW_VERSIONS = ("+", "~")  # latest stable, then latest of any status
_PERIOD_PATTERN = re.compile(r"^\s*(\d{4})-?M?(\d{1,2})")


def _parse_period(label: Any) -> pd.Period | None:
    """Parse IMF period labels such as '1976-M01', '1976-01' or '1976M01' to a monthly Period."""
    if label is None:
        return None
    match = _PERIOD_PATTERN.match(str(label))
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return pd.Period(year=year, month=month, freq="M")


def _to_float(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_sdmx_json(payload: dict) -> dict[pd.Period, float]:
    """Extract {period: value} from an SDMX-JSON (1.0 or 2.0) data message."""
    data = payload.get("data", payload)
    datasets = data.get("dataSets") or []
    structures = data.get("structures")
    if not structures:
        structures = [data["structure"]] if "structure" in data else []
    if not datasets or not structures:
        return {}

    values: dict[pd.Period, float] = {}
    for dataset in datasets:
        struct_index = dataset.get("structure", 0)
        if not isinstance(struct_index, int) or struct_index >= len(structures):
            struct_index = 0
        obs_dims = structures[struct_index].get("dimensions", {}).get("observation", [])
        time_pos = next((i for i, dim in enumerate(obs_dims) if dim.get("id") == "TIME_PERIOD"), 0)
        if not obs_dims:
            continue
        time_values = obs_dims[time_pos].get("values", [])

        observation_maps = [s.get("observations") or {} for s in (dataset.get("series") or {}).values()]
        observation_maps.append(dataset.get("observations") or {})  # flat (AllDimensions) layout
        for observations in observation_maps:
            for obs_key, obs in observations.items():
                parts = str(obs_key).split(":")
                try:
                    time_entry = time_values[int(parts[time_pos])]
                except (IndexError, ValueError):
                    continue
                label = time_entry.get("value") or time_entry.get("id") or time_entry.get("name")
                period = _parse_period(label)
                raw = obs[0] if isinstance(obs, list) and obs else obs
                number = _to_float(raw)
                if period is not None and number is not None:
                    values.setdefault(period, number)
    return values


def _parse_sdmx_xml(content: bytes) -> dict[pd.Period, float]:
    """Extract {period: value} from SDMX-ML (structure-specific or generic) data messages."""
    root = ET.fromstring(content)
    values: dict[pd.Period, float] = {}
    for element in root.iter():
        if _local_name(element.tag) != "Obs":
            continue
        period_label = element.attrib.get("TIME_PERIOD")
        value = element.attrib.get("OBS_VALUE")
        if period_label is None or value is None:  # generic format
            for child in element:
                name = _local_name(child.tag)
                if name == "ObsDimension":
                    period_label = child.attrib.get("value", period_label)
                elif name == "ObsValue":
                    value = child.attrib.get("value", value)
        period = _parse_period(period_label)
        number = _to_float(value)
        if period is not None and number is not None:
            values.setdefault(period, number)
    return values


def _parse_response(response: requests.Response) -> dict[pd.Period, float] | None:
    """Return parsed observations, or None if the body is not a recognizable SDMX message."""
    content_type = response.headers.get("Content-Type", "").lower()
    body = response.content.lstrip()
    try:
        if "json" in content_type or body[:1] in (b"{", b"["):
            return _parse_sdmx_json(response.json())
        if "xml" in content_type or body[:1] == b"<":
            return _parse_sdmx_xml(body)
    except (ValueError, ET.ParseError, KeyError, TypeError, AttributeError):
        return None
    return None


def _to_series(values: dict[pd.Period, float]) -> pd.Series:
    if not values:
        return pd.Series(dtype="float64", index=pd.PeriodIndex([], freq="M"))
    series = pd.Series(values, dtype="float64")
    series.index = pd.PeriodIndex(series.index, freq="M")
    series = series.sort_index()
    series = series[(series.index >= DATA_START) & (series > 0)]
    return series


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_imf_series(dataflow: str, key: str) -> pd.Series:
    """Download one monthly series from the IMF SDMX 3.0 API.

    Returns an empty Series when the IMF reports that the series does not exist.
    Raises IMFDataError when the API cannot be reached or answers with errors.
    """
    params = {"dimensionAtObservation": "TIME_PERIOD", "attributes": "dsd", "measures": "all"}
    errors: list[str] = []
    not_found = False
    for version in _DATAFLOW_VERSIONS:
        url = f"{IMF_BASE_URL}/data/dataflow/{IMF_AGENCY}/{dataflow}/{version}/{key}"
        for accept in _ACCEPT_HEADERS:
            try:
                response = _HTTP.get(url, params=params, headers={"Accept": accept}, timeout=REQUEST_TIMEOUT)
            except requests.RequestException as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                break  # network problem: the next Accept header will not help
            if response.status_code == 404:
                not_found = True
                break  # "no results" in SDMX; try the next dataflow version
            if response.status_code in (406, 415):
                continue  # format not offered; try the next Accept header
            if not response.ok:
                errors.append(f"HTTP {response.status_code} for {response.url}")
                continue
            values = _parse_response(response)
            if values is not None:
                return _to_series(values)
            errors.append(f"Unrecognized response format ({response.headers.get('Content-Type', 'unknown')})")
    if not_found and not errors:
        return _to_series({})
    if not_found and all(e.startswith("HTTP 4") for e in errors):
        return _to_series({})
    raise IMFDataError("; ".join(dict.fromkeys(errors)) or "No usable response from the IMF API.")


def _collect_country_codes(node: Any, found: set[str]) -> None:
    """Walk an availability (content constraint) message and collect COUNTRY values."""
    if isinstance(node, dict):
        if node.get("id") == "COUNTRY" and isinstance(node.get("values"), list):
            for item in node["values"]:
                code = item.get("value") or item.get("id") if isinstance(item, dict) else item
                if isinstance(code, str):
                    found.add(code)
        for child in node.values():
            _collect_country_codes(child, found)
    elif isinstance(node, list):
        for child in node:
            _collect_country_codes(child, found)


def _fetch_available_countries(dataflow: str, key_pattern: str) -> set[str]:
    url = f"{IMF_BASE_URL}/availability/dataflow/{IMF_AGENCY}/{dataflow}/+/{key_pattern}/COUNTRY"
    try:
        response = _HTTP.get(url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT)
        if not response.ok:
            return set()
        found: set[str] = set()
        _collect_country_codes(response.json(), found)
        return found
    except (requests.RequestException, ValueError):
        return set()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def available_country_codes() -> tuple[list[str], bool]:
    """Codes of economies that have both monthly CPI and exchange-rate data.

    Falls back to the full built-in list if the IMF availability service is unavailable.
    Returns (codes, filtered_by_imf_availability).
    """
    cpi_codes = _fetch_available_countries(CPI_DATAFLOW, "*.CPI._T.IX.M")
    er_codes = _fetch_available_countries(ER_DATAFLOW, "*.XDC_USD.PA_RT.M")
    usd_users = {code for code, (_, currency) in COUNTRIES.items() if currency == "USD"}
    if len(cpi_codes) >= 20 and len(er_codes) >= 20:
        usable = {code for code in COUNTRIES if code in cpi_codes and (code in er_codes or code in usd_users)}
        if len(usable) >= 20:
            return sort_codes(usable), True
    return sort_codes(COUNTRIES), False


def sort_codes(codes: Any) -> list[str]:
    """Euro area first, then countries alphabetically by name."""
    codes = set(codes)
    ordered = sorted((c for c in codes if c != EURO_AREA_CODE), key=lambda c: COUNTRIES[c][0])
    return ([EURO_AREA_CODE] if EURO_AREA_CODE in codes else []) + ordered


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------
def lcu_per_usd(iso3: str) -> tuple[pd.Series, str]:
    """Local-currency units per USD for one economy, plus a note about its source.

    For the United States the rate is identically 1 (USD per USD), so it is constructed
    rather than downloaded. Dollarized economies fall back to 1 if the IMF has no series.
    """
    current_month = pd.Timestamp.today().to_period("M")
    ones = pd.Series(1.0, index=pd.period_range(DATA_START, current_month, freq="M"))
    if iso3 == "USA":
        return ones, "USD per USD is identically 1 (constructed, not downloaded)."
    series = fetch_imf_series(ER_DATAFLOW, ER_KEY_TEMPLATE.format(iso3=iso3))
    if series.empty and COUNTRIES[iso3][1] == "USD":
        return ones, "Uses the US dollar; IMF series unavailable, so the rate is set to 1."
    return series, f"IMF ER dataflow, key {ER_KEY_TEMPLATE.format(iso3=iso3)}"


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def build_dataset(iso1: str, iso2: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """Merge IMF data for both economies and compute S(t) and RER(t) for every month."""
    er1, note1 = lcu_per_usd(iso1)
    er2, note2 = lcu_per_usd(iso2)
    cpi1 = fetch_imf_series(CPI_DATAFLOW, CPI_KEY_TEMPLATE.format(iso3=iso1))
    cpi2 = fetch_imf_series(CPI_DATAFLOW, CPI_KEY_TEMPLATE.format(iso3=iso2))

    frame = pd.concat({"lcu_per_usd_1": er1, "lcu_per_usd_2": er2, "cpi_1": cpi1, "cpi_2": cpi2}, axis=1)
    frame = frame.sort_index()
    frame = frame[frame.index >= DATA_START]

    # S(t): Country 2 currency per 1 unit of Country 1 currency (cross rate through the USD).
    frame["S"] = frame["lcu_per_usd_2"] / frame["lcu_per_usd_1"]
    frame["RER"] = frame["S"] * frame["cpi_1"] / frame["cpi_2"]
    frame["valid"] = np.isfinite(frame["RER"]) & (frame["RER"] > 0)

    notes = {
        "er1": note1,
        "er2": note2,
        "cpi1": f"IMF CPI dataflow, key {CPI_KEY_TEMPLATE.format(iso3=iso1)}",
        "cpi2": f"IMF CPI dataflow, key {CPI_KEY_TEMPLATE.format(iso3=iso2)}",
        "missing": ", ".join(
            label
            for label, series in (
                (f"exchange rate for {COUNTRIES[iso1][0]}", er1),
                (f"exchange rate for {COUNTRIES[iso2][0]}", er2),
                (f"CPI for {COUNTRIES[iso1][0]}", cpi1),
                (f"CPI for {COUNTRIES[iso2][0]}", cpi2),
            )
            if series.empty
        ),
    }
    return frame, notes


def compute_sample(frame: pd.DataFrame, start: pd.Period, end: pd.Period) -> tuple[pd.DataFrame, float]:
    """Restrict to [start, end], compute RER* over valid months and the real index."""
    sample = frame.loc[(frame.index >= start) & (frame.index <= end)].copy()
    rer_star = float(sample.loc[sample["valid"], "RER"].mean())
    sample["RER_star"] = rer_star
    sample["real_index"] = np.where(sample["valid"], 100.0 * sample["RER"] / rer_star, np.nan)
    return sample, rer_star


def large_nominal_moves(sample: pd.DataFrame) -> list[tuple[pd.Period, float]]:
    """One-month changes in S(t) above the threshold (devaluations, pegs breaking, redenominations)."""
    s = sample["S"].where(sample["valid"])
    change = s / s.shift(1) - 1.0
    flagged = change[change.abs() > LARGE_MOVE_THRESHOLD].dropna()
    return list(flagged.items())


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------
def month_label(period: pd.Period) -> str:
    return period.strftime("%b %Y")


def format_number(value: float) -> str:
    """Readable number with precision that adapts to magnitude (S can be 0.0001 or 100,000)."""
    if value is None or not np.isfinite(value):
        return "n/a"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 100:
        return f"{value:,.1f}"
    if magnitude >= 1:
        return f"{value:,.3f}"
    if magnitude == 0:
        return "0"
    decimals = min(10, int(-np.floor(np.log10(magnitude))) + 3)
    return f"{value:.{decimals}f}"


def hover_format(series: pd.Series) -> str:
    """Plotly d3 format for hover values of S(t), based on typical magnitude."""
    median = float(series.abs().median()) if series.notna().any() else 1.0
    if median >= 1000:
        return ",.0f"
    if median >= 100:
        return ",.1f"
    if median >= 1:
        return ",.3f"
    return ".4~g" if median >= 0.001 else ".4~e"


def style_axes(fig: go.Figure) -> None:
    fig.update_xaxes(showgrid=False, ticks="outside", tickformat="%Y", showline=True, linewidth=1)
    fig.update_yaxes(showgrid=True, gridwidth=1, zeroline=False)


def build_chart(
    sample: pd.DataFrame,
    view: str,
    name1: str,
    name2: str,
    cur1: str,
    cur2: str,
    log_nominal: bool,
) -> go.Figure:
    x = sample.index.to_timestamp()
    real = sample["real_index"]
    nominal = sample["S"].where(sample["valid"])
    s_unit = f"{cur2} per 1 {cur1}"
    s_fmt = hover_format(nominal)

    real_trace = go.Scatter(
        x=x,
        y=real,
        mode="lines",
        name="Real index (sample avg = 100)",
        line={"color": COLOR_REAL, "width": 2},
        connectgaps=False,
        hovertemplate="%{x|%b %Y}<br>Real index: <b>%{y:.1f}</b><extra></extra>",
    )
    nominal_trace = go.Scatter(
        x=x,
        y=nominal,
        mode="lines",
        name=f"Nominal S(t), {s_unit}",
        line={"color": COLOR_NOMINAL, "width": 2},
        connectgaps=False,
        hovertemplate=f"%{{x|%b %Y}}<br>S(t): <b>%{{y:{s_fmt}}}</b> {s_unit}<extra></extra>",
    )
    real_axis_title = "Index, sample average = 100"
    nominal_axis_title = f"{cur2} per 1 {cur1}"
    nominal_axis_type = "log" if log_nominal else "linear"

    if view == "Both":
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.12,
            subplot_titles=(
                f"Real exchange rate index: {name2} goods per {name1} good (sample average = 100)",
                f"Nominal exchange rate S(t): {s_unit}",
            ),
        )
        fig.add_trace(real_trace, row=1, col=1)
        fig.add_trace(nominal_trace, row=2, col=1)
        fig.add_hline(y=100, line={"color": COLOR_REFERENCE, "width": 1, "dash": "dash"}, row=1, col=1)
        fig.update_yaxes(title_text=real_axis_title, row=1, col=1)
        fig.update_yaxes(title_text=nominal_axis_title, type=nominal_axis_type, row=2, col=1)
        fig.update_layout(height=700)
        for annotation in fig.layout.annotations:  # left-align subplot titles
            annotation.update(x=0, xanchor="left", font={"size": 14})
    elif view == "Real":
        fig = go.Figure(real_trace)
        fig.add_hline(
            y=100,
            line={"color": COLOR_REFERENCE, "width": 1, "dash": "dash"},
            annotation_text="Sample average = 100",
            annotation_position="top left",
        )
        fig.update_layout(
            title={"text": f"Real exchange rate index: {name2} goods per {name1} good", "x": 0, "xanchor": "left"},
            yaxis_title=real_axis_title,
            height=480,
        )
    else:
        fig = go.Figure(nominal_trace)
        fig.update_layout(
            title={"text": f"Nominal exchange rate S(t): {s_unit}", "x": 0, "xanchor": "left"},
            yaxis_title=nominal_axis_title,
            yaxis_type=nominal_axis_type,
            height=480,
        )

    fig.update_layout(
        hovermode="x unified" if view != "Both" else "x",
        showlegend=False,
        margin={"l": 70, "r": 30, "t": 90 if view == "Both" else 70, "b": 50},
    )
    style_axes(fig)
    if view == "Both":
        fig.update_xaxes(showticklabels=True, row=1, col=1)
    return fig


def build_csv(sample: pd.DataFrame, iso1: str, iso2: str, cur1: str, cur2: str) -> bytes:
    out = pd.DataFrame(
        {
            "month": sample.index.strftime("%Y-%m"),
            "country1": COUNTRIES[iso1][0],
            "country2": COUNTRIES[iso2][0],
            f"country1_{iso1}_lcu_per_usd": sample["lcu_per_usd_1"].to_numpy(),
            f"country2_{iso2}_lcu_per_usd": sample["lcu_per_usd_2"].to_numpy(),
            f"S_{cur2}_per_1_{cur1}": sample["S"].to_numpy(),
            f"P1_CPI_{iso1}": sample["cpi_1"].to_numpy(),
            f"P2_CPI_{iso2}": sample["cpi_2"].to_numpy(),
            "RER_S_x_P1_over_P2": sample["RER"].to_numpy(),
            "RER_star_sample_mean": sample["RER_star"].to_numpy(),
            "real_index_100xRER_over_RERstar": sample["real_index"].to_numpy(),
            "valid_month": sample["valid"].to_numpy(),
        }
    )
    return out.to_csv(index=False, float_format="%.10g").encode("utf-8")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Real Exchange Rate Explorer", page_icon="💱", layout="wide")
    st.title("Real Exchange Rate Explorer")
    st.caption(
        "Monthly bilateral nominal and real exchange rates built from IMF CPI and exchange-rate data "
        "(IMF SDMX 3.0 API), January 1976 onward where available."
    )

    with st.spinner("Loading the IMF country list…"):
        codes, filtered = available_country_codes()

    with st.sidebar:
        st.header("1. Countries")
        default1 = codes.index("USA") if "USA" in codes else 0
        default2 = codes.index("JPN") if "JPN" in codes else min(1, len(codes) - 1)
        label = lambda c: f"{COUNTRIES[c][0]} ({COUNTRIES[c][1]})"  # noqa: E731
        iso1 = st.selectbox("Country 1 (base currency)", codes, index=default1, format_func=label)
        iso2 = st.selectbox("Country 2 (quote currency)", codes, index=default2, format_func=label)
        st.caption(
            "Listed: economies with IMF monthly CPI and exchange-rate data."
            if filtered
            else "Listed: IMF member economies and the Euro area (series availability is checked on load)."
        )

    name1, cur1 = COUNTRIES[iso1]
    name2, cur2 = COUNTRIES[iso2]

    if iso1 == iso2:
        st.warning("Choose two different economies for Country 1 and Country 2.")
        st.stop()

    with st.spinner(f"Downloading IMF data for {name1} and {name2}…"):
        try:
            frame, notes = build_dataset(iso1, iso2)
        except IMFDataError as exc:
            st.error(
                "Could not retrieve data from the IMF API. The service may be temporarily unavailable; "
                f"please try again in a minute.\n\nDetails: {exc}"
            )
            st.stop()

    if notes["missing"]:
        st.warning(f"The IMF returned no monthly data for: {notes['missing']}.")

    valid_months = frame.index[frame["valid"]]
    if len(valid_months) == 0:
        st.error(
            f"No month has all four inputs (both exchange rates and both CPIs) for {name1} and {name2}. "
            "Please choose a different pair."
        )
        st.stop()

    # Direction banner: the single most important piece of labeling in the app.
    st.info(
        f"**Exchange-rate direction:** S(t) = **{cur2} per 1 {cur1}**, i.e. the number of {cur2} "
        f"({name2}) needed to buy one {cur1} ({name1}). A **rise** in S(t) or in the real index means "
        f"**the {cur1} strengthens** against the {cur2} (appreciation of Country 1's currency)."
    )

    months = list(pd.period_range(valid_months.min(), valid_months.max(), freq="M"))
    with st.sidebar:
        st.header("2. Sample period")
        start, end = st.select_slider(
            "Start and end month",
            options=months,
            value=(months[0], months[-1]),
            format_func=month_label,
        )
        st.caption(
            f"Data with all four inputs available: {month_label(months[0])} to {month_label(months[-1])}. "
            "RER* and the real index are recomputed for the selected window."
        )
        st.header("3. Chart")
        view = st.radio("Show", ["Real", "Nominal", "Both"], index=2, horizontal=True)
        log_nominal = st.checkbox(
            "Log scale for nominal S(t)",
            value=False,
            help="Useful when the nominal rate moves by orders of magnitude (e.g. high-inflation economies).",
        )

    sample, rer_star = compute_sample(frame, start, end)
    valid_sample = sample[sample["valid"]]
    if valid_sample.empty:
        st.error("The selected window contains no month with complete data. Widen the sample period.")
        st.stop()

    first, last = valid_sample.iloc[0], valid_sample.iloc[-1]
    first_month, last_month = valid_sample.index[0], valid_sample.index[-1]
    real_change = (last["real_index"] / first["real_index"] - 1.0) * 100.0
    nominal_change = (last["S"] / first["S"] - 1.0) * 100.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        f"Real index, {month_label(last_month)}",
        f"{last['real_index']:.1f}",
        f"{last['real_index'] - 100:+.1f} vs. sample average",
        help="100 × RER(t) / RER*. Above 100: Country 1's currency is stronger in real terms than its sample average.",
    )
    col2.metric(
        f"Nominal S, {month_label(last_month)}",
        format_number(last["S"]),
        help=f"{cur2} per 1 {cur1}, in actual currency units.",
    )
    col2.caption(f"{cur2} per 1 {cur1}")
    col3.metric(
        "Real change over sample",
        f"{real_change:+.1f}%",
        help=f"Change in the real index from {month_label(first_month)} to {month_label(last_month)}. "
        f"Positive = real appreciation of the {cur1} ({name1}).",
    )
    col4.metric(
        "Nominal change over sample",
        f"{nominal_change:+.1f}%",
        help=f"Change in S(t) from {month_label(first_month)} to {month_label(last_month)}. "
        f"Positive = {cur1} buys more {cur2}.",
    )

    fig = build_chart(sample, view, name1, name2, cur1, cur2, log_nominal)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

    position = "above" if last["real_index"] > 100 else "below"
    st.markdown(
        f"**Reading the chart.** In {month_label(last_month)} the real index is **{last['real_index']:.1f}**, "
        f"{abs(last['real_index'] - 100):.1f}% {position} its {month_label(start)}–{month_label(end)} average. "
        f"{'Above' if position == 'above' else 'Below'} 100 means a basket of {name1} goods buys "
        f"{'more' if position == 'above' else 'fewer'} {name2} goods than on average over the sample, "
        f"so the {cur1} is {'stronger (real appreciation)' if position == 'above' else 'weaker (real depreciation)'} "
        f"relative to that benchmark. The nominal rate S(t) is shown in actual {cur2} per {cur1} and is not normalized."
    )

    n_invalid = int((~sample["valid"]).sum())
    st.caption(
        f"RER* (mean of RER over {len(valid_sample)} valid months in the window) = {format_number(rer_star)}. "
        "The level of RER depends on the CPI base years, so only its changes and the normalized index are meaningful."
        + (f" {n_invalid} month(s) in the window lack at least one input and are excluded." if n_invalid else "")
    )

    moves = large_nominal_moves(sample)
    if moves:
        listed = ", ".join(f"{month_label(p)} ({c * 100:+.0f}%)" for p, c in moves[:6])
        more = f" and {len(moves) - 6} more" if len(moves) > 6 else ""
        st.warning(
            f"Large one-month moves in S(t) (over {LARGE_MOVE_THRESHOLD:.0%}): {listed}{more}. These usually reflect "
            "devaluations or the end of a peg, but can also reflect currency redenominations or breaks in the IMF series."
        )

    st.download_button(
        "Download CSV of the selected sample",
        data=build_csv(sample, iso1, iso2, cur1, cur2),
        file_name=f"rer_{iso1}_{iso2}_{start.strftime('%Y%m')}_{end.strftime('%Y%m')}.csv",
        mime="text/csv",
        type="primary",
    )

    with st.expander("Data table (selected sample)"):
        table = pd.DataFrame(
            {
                f"{name1}: {cur1} per USD": sample["lcu_per_usd_1"],
                f"{name2}: {cur2} per USD": sample["lcu_per_usd_2"],
                f"S(t): {cur2} per 1 {cur1}": sample["S"],
                f"P1: CPI {name1}": sample["cpi_1"],
                f"P2: CPI {name2}": sample["cpi_2"],
                "RER = S×P1/P2": sample["RER"],
                "Real index": sample["real_index"],
                "Valid": sample["valid"],
            }
        )
        table.index = sample.index.strftime("%Y-%m")
        table.index.name = "Month"
        st.dataframe(table, width="stretch")

    with st.expander("Methodology and data sources"):
        st.markdown(
            f"""
**Data (IMF SDMX 3.0 API, `{IMF_BASE_URL}`)**
- CPI, monthly index: key `{{ISO3}}.CPI._T.IX.M` in dataflow `{IMF_AGENCY}/{CPI_DATAFLOW}`
- Exchange rate, local currency per USD, period average: key `{{ISO3}}.XDC_USD.PA_RT.M` in dataflow `{IMF_AGENCY}/{ER_DATAFLOW}`
- The Euro area uses IMF code `{EURO_AREA_CODE}`.

**Sources for this pair**
- {name1} exchange rate: {notes['er1']}
- {name2} exchange rate: {notes['er2']}
- {name1} CPI: {notes['cpi1']}
- {name2} CPI: {notes['cpi2']}

**Calculations**
"""
        )
        st.latex(r"S(t) = \frac{\text{Country 2 LCU per USD}}{\text{Country 1 LCU per USD}} \quad [\text{Country 2 currency per 1 unit of Country 1 currency}]")
        st.latex(r"RER(t) = S(t)\,\frac{P_1(t)}{P_2(t)}")
        st.latex(r"RER^{*} = \frac{1}{N}\sum_{t \in \text{sample, valid}} RER(t), \qquad \text{Real Index}(t) = 100\,\frac{RER(t)}{RER^{*}}")
        st.markdown(
            f"""
- A month is **valid** when both exchange rates and both CPIs are available and positive.
- For the United States, USD per USD is identically 1, so S(t) equals the other country's rate against the dollar
  (or its inverse, depending on which side the US is on).
- RER(t) measures how many baskets of {name2} goods one basket of {name1} goods buys. Because each CPI has its own
  base year, the level of RER(t) is arbitrary; normalizing by the sample mean makes the index read as
  "percent above or below the average real exchange rate of the selected period".
- If relative PPP held exactly, the real index would stay at 100. Persistent swings away from 100 are real
  appreciations/depreciations.
- IMF data are cached for 24 hours.
"""
        )


if __name__ == "__main__":
    main()
