#!/usr/bin/env python3
"""
Phase 0: Ingest PnL CSV and optional holdings (CAS PDF or CSV).
Produces: holdings.csv, closed_pnl.csv, portfolio_summary.json.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

# Config: use portfolio-analyzer config when available
try:
    from config import (
        PNL_CSV,
        HOLDINGS_CSV,
        HOLDINGS_CSV_OUT,
        CLOSED_PNL_CSV,
        PORTFOLIO_SUMMARY_JSON,
        OUTPUT_DIR,
        CAS_PDF,
    )
except ImportError:
    PORTFOLIO_ANALYZER = Path(__file__).resolve().parent
    PNL_CSV = PORTFOLIO_ANALYZER / "8500589913_EQProfitLossDetails.csv"
    HOLDINGS_CSV = PORTFOLIO_ANALYZER / "holdings_export.csv"
    CAS_PDF = PORTFOLIO_ANALYZER / "NSDLe-CAS_104270072_JAN_2026.PDF"
    OUTPUT_DIR = PORTFOLIO_ANALYZER / "output"
    HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
    CLOSED_PNL_CSV = OUTPUT_DIR / "closed_pnl.csv"
    PORTFOLIO_SUMMARY_JSON = OUTPUT_DIR / "portfolio_summary.json"
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# ISIN pattern (Indian equities: INE + 9 or 10 alphanumeric)
ISIN_RE = re.compile(r"^INE[A-Z0-9]{9,10}$", re.I)


def _parse_date(s: str) -> datetime | None:
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_float(s: str) -> float | None:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(s: str) -> int | None:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    try:
        return int(float(str(s).strip().replace(",", "")))
    except ValueError:
        return None


def _is_isin(val: str) -> bool:
    return bool(val and ISIN_RE.match(str(val).strip()))


def parse_pnl_csv(path: Path) -> tuple[pd.DataFrame, dict]:
    """
    Parse broker PnL CSV. Returns (closed_pnl DataFrame, meta dict with account_name, account_id).
    """
    meta = {"account_id": "", "account_name": "", "report_type": "Equity PL"}
    rows = []
    header = ["Stock Symbol", "ISIN", "Qty", "Sale Date", "Sale Rate", "Sale Value",
              "Purchase Date", "Purchase Rate", "Purchase Value", "Profit/Loss(-)"]

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            # Meta rows
            if len(row) >= 2 and str(row[0]).strip().lower() == "account":
                meta["account_id"] = str(row[1]).strip()
                continue
            if len(row) >= 2 and str(row[0]).strip().lower() == "name":
                meta["account_name"] = str(row[1]).strip()
                continue
            # Header row
            if len(row) >= 10 and str(row[0]).strip() == "Stock Symbol":
                continue
            # Section header (e.g. "Intraday (Sold same day )", "<= 1 Year Profit/Loss...")
            if len(row) < 10 or not _is_isin(row[1] if len(row) > 1 else ""):
                continue
            # Data row: Symbol, ISIN, Qty, Sale Date, Sale Rate, Sale Value, Purchase Date, Purchase Rate, Purchase Value, P/L
            sym = str(row[0]).strip().upper()
            isin = str(row[1]).strip()
            qty = _parse_int(row[2])
            sale_d = _parse_date(row[3])
            sale_rate = _parse_float(row[4])
            sale_val = _parse_float(row[5])
            purchase_d = _parse_date(row[6])
            purchase_rate = _parse_float(row[7])
            purchase_val = _parse_float(row[8])
            pnl = _parse_float(row[9])

            if sym and isin and qty is not None and sale_d and purchase_d:
                # Tenure bucket
                if sale_d.date() == purchase_d.date():
                    tenure_bucket = "intraday"
                elif (sale_d - purchase_d).days <= 365:
                    tenure_bucket = "STCG"  # Short-term
                else:
                    tenure_bucket = "LTCG"  # Long-term

                rows.append({
                    "symbol": sym,
                    "isin": isin,
                    "qty": qty,
                    "purchase_date": purchase_d.strftime("%Y-%m-%d"),
                    "purchase_rate": purchase_rate,
                    "purchase_value": purchase_val,
                    "sale_date": sale_d.strftime("%Y-%m-%d"),
                    "sale_rate": sale_rate,
                    "sale_value": sale_val,
                    "pnl": pnl,
                    "tenure_bucket": tenure_bucket,
                })

    df = pd.DataFrame(rows)
    return df, meta


def _clean_numeric_series(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        .str.replace(r"^\+\s*", "", regex=True)
        .str.replace(r"^-\s+", "-", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def load_holdings_csv(path: Path) -> pd.DataFrame | None:
    """Load holdings from a CSV (Symbol, ISIN, Quantity, etc.). Returns None if file missing or empty."""
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    df = df.dropna(axis=1, how="all")

    normalized: dict[str, str] = {}
    for c in df.columns:
        key = str(c).lower().strip()
        key = re.sub(r"\s+", " ", key)
        if key in ("symbol", "stock symbol", "scrip", "scrip code"):
            normalized[c] = "symbol"
        elif key in ("isin", "isin code"):
            normalized[c] = "isin"
        elif key in ("qty", "quantity", "qty."):
            normalized[c] = "quantity"
        elif key in ("value_rs", "value", "market value", "value at market price", "amount"):
            normalized[c] = "value_rs"
        elif key in ("current market price", "current price", "market price", "ltp"):
            normalized[c] = "current_price"
        elif key in ("average cost price", "average price", "avg cost", "avg price"):
            normalized[c] = "average_cost_price"
        elif key == "company name":
            normalized[c] = "company_name"

    df = df.rename(columns=normalized)
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
        df["broker_symbol"] = df["symbol"]
    if "isin" in df.columns:
        df["isin"] = df["isin"].astype(str).str.strip().str.upper()
    for col in ("quantity", "value_rs", "current_price", "average_cost_price"):
        if col in df.columns:
            df[col] = _clean_numeric_series(df[col])
    if "value_rs" not in df.columns and {"quantity", "current_price"}.issubset(df.columns):
        df["value_rs"] = df["quantity"].fillna(0) * df["current_price"].fillna(0)
    if "quantity" in df.columns:
        df = df[df["quantity"].fillna(0) > 0]
    if df.empty:
        return None
    if "symbol" in df.columns:
        try:
            from portfolio_symbol_mapper import resolve_symbol

            mapped_symbols = []
            methods = []
            scores = []
            matched_names = []
            for _, row in df.iterrows():
                match = resolve_symbol(
                    broker_symbol=row.get("broker_symbol") or row.get("symbol"),
                    company_name=row.get("company_name") or "",
                )
                mapped_symbols.append(match.symbol)
                methods.append(match.method)
                scores.append(round(match.score, 4))
                matched_names.append(match.matched_name)
            df["symbol"] = mapped_symbols
            df["symbol_mapping_method"] = methods
            df["symbol_mapping_score"] = scores
            df["symbol_mapping_name"] = matched_names
        except Exception:
            df["symbol_mapping_method"] = "not_attempted"
            df["symbol_mapping_score"] = 0.0
            df["symbol_mapping_name"] = ""
    return df


def apply_llm_symbol_mapping(
    holdings_df: pd.DataFrame,
    *,
    model: str = "gpt-4o",
) -> pd.DataFrame:
    """Use GPT-4o to adjudicate rows not confidently mapped by local rules."""
    if holdings_df is None or holdings_df.empty or "symbol_mapping_method" not in holdings_df.columns:
        return holdings_df
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    try:
        from openai import OpenAI
        from portfolio_symbol_mapper import resolve_symbol_with_llm
    except Exception:
        holdings_df["llm_mapping_status"] = "unavailable"
        return holdings_df

    client = OpenAI()
    df = holdings_df.copy()
    statuses = []
    rationales = []
    for idx, row in df.iterrows():
        method = str(row.get("symbol_mapping_method") or "")
        if method not in {"unmapped", "ambiguous"}:
            statuses.append("not_needed")
            rationales.append("")
            continue
        match = resolve_symbol_with_llm(
            broker_symbol=row.get("broker_symbol") or row.get("symbol"),
            company_name=row.get("company_name") or "",
            client=client,
            model=model,
        )
        statuses.append(match.method)
        rationales.append(match.rationale)
        if match.method == "llm":
            df.at[idx, "symbol"] = match.symbol
            df.at[idx, "symbol_mapping_method"] = "llm"
            df.at[idx, "symbol_mapping_score"] = match.score
            df.at[idx, "symbol_mapping_name"] = match.matched_name
    df["llm_mapping_status"] = statuses
    df["llm_mapping_rationale"] = rationales
    return df


def extract_holdings_from_cas_pdf(pdf_path: Path, password: str | None = None) -> pd.DataFrame | None:
    """
    Extract equity holdings from NSDL/CDSL CAS PDF (Consolidated Account Statement).
    Uses pdfplumber to find tables with ISIN and quantity columns.
    Returns DataFrame with columns symbol, isin, quantity (and value if present), or None if failed.
    PDF may be password-protected; set CAS_PDF_PASSWORD env or pass password=.
    """
    try:
        import pdfplumber
    except ImportError:
        return None
    if not pdf_path.exists():
        return None
    pw = password or __import__("os").environ.get("CAS_PDF_PASSWORD", "")
    try:
        with pdfplumber.open(pdf_path, password=pw if pw else None) as pdf:
            all_rows = []
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    header = [str(c or "").strip().lower() for c in table[0]]
                    # Look for ISIN and quantity columns (NSDL CAS typical: Security Description, ISIN, Qty, etc.)
                    isin_col = None
                    qty_col = None
                    sym_col = None
                    val_col = None
                    for i, h in enumerate(header):
                        if "isin" in h and "description" not in h:
                            isin_col = i
                        if "qty" in h or "quantity" in h or "bal qty" in h or ("shares" in h and "no" in h):
                            qty_col = i
                        if "security" in h or "scrip" in h or ("symbol" in h and "isin" not in h) or "company name" in h:
                            sym_col = i
                        if ("value" in h and "nav" not in h) or "market value" in h:
                            val_col = i
                    if isin_col is None or qty_col is None:
                        continue
                    for row in table[1:]:
                        if not row or len(row) <= max(isin_col, qty_col):
                            continue
                        raw_isc = str(row[isin_col] or "").strip()
                        # NSDL CAS often has "ISIN\nSYMBOL.NSE" in first column
                        isin = raw_isc.split("\n")[0].strip() if raw_isc else ""
                        if not isin or not isin.startswith("INE"):
                            continue
                        if not _is_isin(isin):
                            continue
                        qty_val = _parse_int(row[qty_col])
                        if qty_val is None or qty_val <= 0:
                            continue
                        sym = ""
                        if "\n" in raw_isc:
                            sym = raw_isc.split("\n", 1)[1].strip().upper()
                            for suffix in (".NSE", ".BSE"):
                                if sym.endswith(suffix):
                                    sym = sym[: -len(suffix)]
                                    break
                        if not sym and sym_col is not None and len(row) > sym_col:
                            sym = str(row[sym_col] or "").strip().upper()
                        if not sym:
                            sym = isin
                        val = _parse_float(row[val_col]) if val_col is not None and len(row) > val_col else None
                        all_rows.append({"symbol": sym or isin, "isin": isin, "quantity": qty_val, "value_rs": val})
            if not all_rows:
                return None
            return pd.DataFrame(all_rows)
    except Exception:
        return None


_DEFAULT = object()


def run_phase0(
    pnl_csv: Path | None | object = _DEFAULT,
    holdings_csv: Path | None = None,
    cas_pdf: Path | None = None,
    require_pnl: bool = True,
    use_llm_mapping: bool = False,
    llm_mapping_model: str = "gpt-4o",
) -> tuple[pd.DataFrame, pd.DataFrame | None, dict]:
    """
    Run Phase 0 ingest.
    - pnl_csv: path to PnL CSV (default from config).
    - holdings_csv: optional path to holdings CSV export.
    - cas_pdf: optional CAS PDF (parsing not implemented yet; use holdings_csv for now).
    Returns (closed_pnl_df, holdings_df_or_none, portfolio_summary).
    """
    pnl_path = PNL_CSV if pnl_csv is _DEFAULT else pnl_csv
    closed_pnl_columns = [
        "symbol",
        "isin",
        "qty",
        "purchase_date",
        "purchase_rate",
        "purchase_value",
        "sale_date",
        "sale_rate",
        "sale_value",
        "pnl",
        "tenure_bucket",
    ]
    if pnl_path is not None and Path(pnl_path).exists():
        closed_pnl, meta = parse_pnl_csv(Path(pnl_path))
    elif require_pnl:
        raise FileNotFoundError(f"PnL CSV not found: {pnl_path}")
    else:
        closed_pnl = pd.DataFrame(columns=closed_pnl_columns)
        meta = {"account_id": "", "account_name": "", "report_type": "Holdings only"}
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

    # Closed PnL output
    closed_pnl.to_csv(CLOSED_PNL_CSV, index=False)
    total_pnl = closed_pnl["pnl"].sum() if not closed_pnl.empty else 0
    symbols = closed_pnl["symbol"].unique().tolist() if not closed_pnl.empty else []

    summary = {
        "account_id": meta.get("account_id"),
        "account_name": meta.get("account_name"),
        "report_type": meta.get("report_type"),
        "closed_trades_count": len(closed_pnl),
        "unique_symbols_traded": len(symbols),
        "total_realized_pnl": round(float(total_pnl), 2),
        "pnl_by_tenure": closed_pnl.groupby("tenure_bucket")["pnl"].sum().round(2).to_dict() if not closed_pnl.empty else {},
        "data_as_of": closed_pnl["sale_date"].max() if not closed_pnl.empty else None,
    }

    # Holdings: from CSV if provided, else try CAS PDF
    holdings_df = None
    holdings_path = holdings_csv or HOLDINGS_CSV
    if holdings_path.exists():
        holdings_df = load_holdings_csv(holdings_path)
        if holdings_df is not None and not holdings_df.empty:
            if use_llm_mapping:
                holdings_df = apply_llm_symbol_mapping(holdings_df, model=llm_mapping_model)
            holdings_df.to_csv(HOLDINGS_CSV_OUT, index=False)
            summary["holdings_count"] = len(holdings_df)
            summary["holdings_source"] = "holdings_export.csv"
    if holdings_df is None or holdings_df.empty:
        pdf_path = cas_pdf
        if pdf_path is None:
            try:
                from config import CAS_PDF as _cas
                pdf_path = _cas
            except Exception:
                pdf_path = Path(__file__).resolve().parent / "NSDLe-CAS_104270072_JAN_2026.PDF"
        if pdf_path and Path(pdf_path).exists():
            pdf_password = __import__("os").environ.get("CAS_PDF_PASSWORD")
            holdings_df = extract_holdings_from_cas_pdf(Path(pdf_path), password=pdf_password)
            if holdings_df is not None and not holdings_df.empty:
                if use_llm_mapping:
                    holdings_df = apply_llm_symbol_mapping(holdings_df, model=llm_mapping_model)
                holdings_df.to_csv(HOLDINGS_CSV_OUT, index=False)
                summary["holdings_count"] = len(holdings_df)
                summary["holdings_source"] = "CAS PDF"
        if holdings_df is None or holdings_df.empty:
            summary["holdings_count"] = 0
            summary["holdings_note"] = (
                "CAS PDF not parsed (password-protected or no tables). Set CAS_PDF_PASSWORD env or export holdings to holdings_export.csv."
                if pdf_path and Path(pdf_path).exists() else
                "No holdings file provided. Add holdings_export.csv or parse CAS PDF (set CAS_PDF_PASSWORD if PDF is protected)."
            )

    with open(PORTFOLIO_SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return closed_pnl, holdings_df, summary


if __name__ == "__main__":
    closed, holdings, summary = run_phase0()
    print("Phase 0 done.")
    print(f"  Closed PnL: {len(closed)} rows -> {CLOSED_PNL_CSV}")
    print(f"  Total realized PnL: {summary.get('total_realized_pnl')}")
    print(f"  Holdings: {summary.get('holdings_count', 0)} (from CSV)" if holdings is None or holdings.empty else f"  Holdings: {len(holdings)} rows -> {HOLDINGS_CSV_OUT}")
    print(f"  Summary: {PORTFOLIO_SUMMARY_JSON}")
