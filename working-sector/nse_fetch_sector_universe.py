#!/usr/bin/env python3
"""
Download Plastics and Packaging (or other sector) stocks from NSE and save as universe CSV.

Uses NSE website session (cookies + Referer) to call:
- equity-stockIndices: get index constituents (e.g. NIFTY 500)
- quote-equity: get company name and industry per symbol (when available)

Filters symbols by industry/subindustry containing: Plastic, Packaging, Polymer, Films
(flexible packaging), Moulding, etc. Writes SYMBOL, NAME, SOURCE, SUBSECTOR.

Usage:
  python nse_fetch_sector_universe.py
  python nse_fetch_sector_universe.py --sector plastics_and_packaging
  NSE_SECTOR=plastics_and_packaging python nse_fetch_sector_universe.py

Output: working-sector/<sector>_universe.csv
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

WORKING_SECTOR = Path(__file__).resolve().parent
if str(WORKING_SECTOR) not in sys.path:
    sys.path.insert(0, str(WORKING_SECTOR))

# Keywords to match NSE industry/subindustry for "Plastics and Packaging"
PLASTICS_PACKAGING_KEYWORDS = (
    "plastic",
    "packaging",
    "polymer",
    "films",
    "film",
    "moulding",
    "molding",
    "flexible packaging",
    "rigid packaging",
    "containers",
    "polyplex",
    "cosmo films",
    "bottles",
    "lamination",
)

# Curated fallback list (NSE symbols) when API does not return industry
# Source: NSE industry classification, broker sector lists, existing universe
CURATED_PLASTICS_PACKAGING: list[tuple[str, str, str]] = [
    ("SUPREMEIND", "Supreme Industries", "Plastics"),
    ("FINOPB", "Finolex Industries", "Plastics"),
    ("COSMOFILMS", "Cosmo Films", "Films"),
    ("POLYPLEX", "Polyplex Corporation", "Films/Packaging"),
    ("UFLEX", "UFlex", "Flexible Packaging"),
    ("JINDALPOLY", "Jindal Poly Films", "Films"),
    ("GARFAR", "Garware Hi-Tech Films", "Films"),
    ("SAFARI", "Safari Industries", "Plastics"),
    ("VIPIND", "VIP Industries", "Plastics/Luggage"),
    ("NILKAMAL", "Nilkamal", "Plastics"),
    ("EPL", "EPL", "Packaging"),
    ("AGIGREEN", "AGI Greenpac", "Packaging"),
    ("TCPLPACK", "TCPL Packaging", "Packaging"),
    ("XPROINDIA", "Xpro India", "Packaging"),
    ("SHAILY", "Shaily Engineering Plastics", "Engineering Plastics"),
    ("ALLTIME", "All Time Plastics", "Plastics"),
    ("AMNPLST", "Amines & Plasticizers", "Plasticizers"),
    ("MEGAFLEX", "Mega Flex Plastics", "Plastics"),
    ("TAINWALCHM", "Tainwala Chemical and Plastic", "Plastics/Chemicals"),
    ("TULSI", "Tulsi Extrusions", "Plastics"),
    ("MAHAPEX", "Maharashtra Polybutenes", "Plastics"),
    ("POLYMED", "Poly Medicure", "Medical Plastics"),
    ("NAHARIND", "Nahar Industrial", "Textiles/Plastics"),
]


def _nse_session():
    """Build requests session with NSE cookies (visit homepage first)."""
    try:
        import requests
    except ImportError:
        raise SystemExit("Install requests: pip install requests")
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        s.get("https://www.nseindia.com", timeout=15)
    except Exception as e:
        print(f"Warning: Could not get NSE cookies: {e}")
    return s


def fetch_index_constituents(session, index_name: str = "NIFTY 500") -> list[dict] | None:
    """Fetch equity list for an index. Returns list of {symbol, meta: {companyName, industry}}."""
    url = "https://www.nseindia.com/api/equity-stockIndices"
    params = {"index": index_name}
    try:
        r = session.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return None
    except Exception as e:
        print(f"Fetch index error: {e}")
        return None


def industry_matches(industry_str: str | None, subindustry_str: str | None) -> bool:
    """True if industry/subindustry suggests Plastics and Packaging."""
    if not industry_str and not subindustry_str:
        return False
    text = " ".join(filter(None, [industry_str or "", subindustry_str or ""])).lower()
    return any(kw in text for kw in PLASTICS_PACKAGING_KEYWORDS)


def name_matches(name: str | None) -> bool:
    """True if company name suggests Plastics and Packaging."""
    if not name:
        return False
    n = name.lower()
    return any(kw in n for kw in PLASTICS_PACKAGING_KEYWORDS + ("poly", "flex", "film", "pack"))


def fetch_plastics_packaging_from_nse(session) -> list[tuple[str, str, str]]:
    """
    Get Plastics & Packaging stocks from NSE equity-stockIndices.
    Response has data[].symbol and data[].meta.{companyName, industry}; filter by industry/name.
    """
    out: list[tuple[str, str, str]] = []
    for index_name in ("NIFTY 500", "NIFTY 200", "NIFTY 50", "SECURITIES IN F&O"):
        raw = fetch_index_constituents(session, index_name)
        if not raw:
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            sym = (item.get("symbol") or item.get("Symbol") or "").strip()
            if not sym:
                continue
            meta = item.get("meta") or {}
            if not isinstance(meta, dict):
                meta = {}
            company_name = meta.get("companyName") or item.get("companyName") or sym
            industry = meta.get("industry") or meta.get("Industry") or ""
            subindustry = meta.get("subindustry") or meta.get("Subindustry") or ""
            if industry_matches(industry, subindustry) or name_matches(company_name):
                sub = (subindustry or industry or "Plastics/Packaging").strip()
                out.append((sym, str(company_name), sub))
        if out:
            break
    return out


def build_curated_universe() -> list[tuple[str, str, str]]:
    """Return curated list as (symbol, name, subsector) with SOURCE NSE/Industry."""
    return [(s, n, sub) for s, n, sub in CURATED_PLASTICS_PACKAGING]


def fetch_and_save(
    sector_key: str = "plastics_and_packaging",
    output_path: Path | None = None,
    use_nse_api: bool = True,
) -> Path:
    """
    Fetch Plastics and Packaging stocks (from NSE when possible, else curated), write universe CSV.
    Returns path to written file.
    """
    if output_path is None:
        output_path = WORKING_SECTOR / f"{sector_key}_universe.csv"
    output_path = Path(output_path)
    rows: list[tuple[str, str, str]] = []
    source_used = "NSE/Curated"
    if use_nse_api:
        try:
            session = _nse_session()
            rows = fetch_plastics_packaging_from_nse(session)
            if rows:
                source_used = "NSE/API"
        except Exception as e:
            print(f"NSE API failed: {e}; using curated list.")
    if not rows:
        rows = build_curated_universe()
    # Deduplicate by symbol, keep first
    seen: set[str] = set()
    unique: list[tuple[str, str, str]] = []
    for s, n, sub in rows:
        s = str(s).strip().upper()
        if s and s not in seen:
            seen.add(s)
            unique.append((s, (n or s).strip(), (sub or "Plastics/Packaging").strip()))
    lines = ["SYMBOL,NAME,SOURCE,SUBSECTOR"]
    for sym, name, sub in unique:
        name_esc = name.replace('"', '""')
        if "," in name or '"' in name:
            name_esc = f'"{name_esc}"'
        lines.append(f"{sym},{name_esc},{source_used},{sub}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(unique)} symbols to {output_path} (source: {source_used})")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Download Plastics and Packaging sector stocks from NSE")
    parser.add_argument("--sector", default="plastics_and_packaging", help="Sector key for filename (default: plastics_and_packaging)")
    parser.add_argument("--no-nse", action="store_true", help="Skip NSE API; use curated list only")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV path (default: working-sector/<sector>_universe.csv)")
    args = parser.parse_args()
    sector = os.environ.get("NSE_SECTOR", args.sector).strip().lower().replace(" ", "_")
    fetch_and_save(sector_key=sector, output_path=args.output, use_nse_api=not args.no_nse)


if __name__ == "__main__":
    main()
