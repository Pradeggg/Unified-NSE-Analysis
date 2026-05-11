"""
P3-2 — Voice Briefing (60-second daily audio).

PG-voice: Generates a concise audio market briefing from already-computed report data.
Pulls from:
  - data/signal_log.csv  → today's candidates, regime, FII flow signal
  - regime_detector.detect_regime()  → latest regime + confidence (live)
  - fetch_fii_dii_flows.load_flow_signals()  → latest flow signals (live)

Outputs (in reports/voice_briefings/):
  - briefing_<YYYY-MM-DD>.txt   → script (always written)
  - briefing_<YYYY-MM-DD>.mp3   → OpenAI TTS (if OPENAI_API_KEY set)
  - briefing_<YYYY-MM-DD>.aiff  → macOS `say` fallback (if OpenAI unavailable)

Design decisions:
  - Reads signal_log.csv (already populated by sector_rotation_report.py) instead of
    re-running the heavy pipeline. Keeps this script fast (< 5s without TTS).
  - TTS is OPTIONAL. If no API key, the .txt script is still produced — never a
    hard failure, consistent with project's "missing data ≠ blocker" pattern.
  - Voice = "cedar" by default for a grounded market-assistant tone.
    Override via $OPENAI_TTS_VOICE or $VOICE.

Usage:
    python3 generate_voice_briefing.py                    # uses today's signals
    python3 generate_voice_briefing.py --date 2026-05-09  # specific date
    python3 generate_voice_briefing.py --no-tts           # script only

Spec source: docs/BACKLOG.md → P3-2.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# PG-voice: load .env so OPENAI_API_KEY is available without manual export.
# Uses python-dotenv if installed, else a tiny inline parser.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    _env_path = Path(__file__).resolve().parent / ".env"
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import pandas as pd

ROOT = Path(__file__).resolve().parent
SIGNAL_LOG = ROOT / "data" / "signal_log.csv"
OUTPUT_DIR = ROOT / "reports" / "voice_briefings"
# PG-voice: index history (Nifty 50, Nifty Bank, etc.) for the daily indices recap.
INDEX_DATA = ROOT / "data" / "nse_index_data.csv"
# PG-voice: cache LLM-generated one-line company descriptions to avoid repeat API calls.
COMPANY_DESC_CACHE = ROOT / "data" / "company_descriptions_cache.json"
# PG-voice: which indices to narrate, in order. Names must match SYMBOL column in INDEX_DATA.
HEADLINE_INDICES = [
    ("Nifty 50",       "Nifty 50"),
    ("Nifty Bank",     "Nifty Bank"),
    ("Nifty Next 50",  "Nifty Next 50"),
    ("Nifty 500",      "Nifty 500"),
]
DEFAULT_VOICE = os.environ.get("OPENAI_TTS_VOICE") or os.environ.get("VOICE", "cedar")
# PG-voice: gpt-4o-mini-tts is the newest model and supports an `instructions` param
# for tone/pacing/affect.
DEFAULT_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
DEFAULT_MAC_VOICE = os.environ.get("VOICE_MAC", "Samantha")  # macOS `say` voice. Try: Daniel, Karen, Allison.
DEFAULT_MAC_RATE = int(os.environ.get("VOICE_RATE", "175"))  # words/min. 200=fast, 175=conversational, 150=slow.

# PG-voice: instructions string sent to gpt-4o-mini-tts. Drives prosody, pace, tone.
# This is what makes the voice sound human: warm opener, professional middle,
# emphatic stock names, slight pauses at section breaks.
VOICE_INSTRUCTIONS = (
    "Persona: a seasoned Indian equity market analyst with 20+ years on the desk — think a senior "
    "sell-side strategist briefing portfolio managers before market open. Speaks with quiet authority, "
    "genuine warmth, and dry conviction. First-person voice (‘I’m watching’, ‘what I like here’, ‘my read’). "
    "Tone: warm, personal, conversational — like talking to a trusted client over chai, not reading a teleprompter. "
    "Confident but humble; never hyped, never robotic. Tiny touches of inflection where it matters. "
    "Pacing: unhurried, around 145–155 words per minute. Pause for a beat after the greeting. "
    "Take a clear breath between sections (regime, flows, sector leadership, top picks, watchlist, sign-off). "
    "Slow down and lean slightly into stock names, company names, and key numbers — entry, stop, target. "
    "Em-dashes are short pauses; periods are slightly longer; ellipses are thoughtful pauses. "
    "Pronunciation: NSE as ‘N-S-E’, FII as ‘F-I-I’, DII as ‘D-I-I’, RSI as ‘R-S-I’, PCR as ‘P-C-R’, F-and-O as ‘F and O’. "
    "Read uppercase tickers letter-by-letter (e.g. ATGL as ‘A-T-G-L’). Read full company names naturally as words. "
    "Read ‘crores’ clearly; read percentages as ‘percent’; read rupee amounts as ‘X rupees’. "
    "Emotion arc: open with genuine, smiling warmth on the greeting; settle into calm, factual confidence "
    "through regime and flows; lean in slightly with conviction on the top picks; close with a measured, "
    "reassuring, almost mentor-like sign-off. Sound like someone who actually cares whether the listener makes money."
)


# ─────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────

def _load_signals_for_date(date_str: str | None = None) -> pd.DataFrame:
    """Load signal_log rows for the given date (default: most recent date in log)."""
    if not SIGNAL_LOG.exists():
        return pd.DataFrame()
    df = pd.read_csv(SIGNAL_LOG)
    if df.empty or "date_issued" not in df.columns:
        return df

    if date_str is None:
        date_str = str(df["date_issued"].max())
    return df[df["date_issued"].astype(str) == date_str].copy()


def _load_regime() -> dict:
    """Live regime via regime_detector. Falls back to {} on any failure."""
    try:
        from regime_detector import detect_regime
        return detect_regime() or {}
    except Exception as exc:
        print(f"  regime detection unavailable ({type(exc).__name__}); using signal_log fallback.")
        return {}


def _load_flows() -> dict:
    """Live FII/DII flow signals. Falls back to {} on any failure."""
    try:
        from fetch_fii_dii_flows import load_flow_signals
        return load_flow_signals() or {}
    except Exception as exc:
        print(f"  flow signals unavailable ({type(exc).__name__}); skipping flow line.")
        return {}


# ─────────────────────────────────────────────
# Script assembly
# ─────────────────────────────────────────────

_FLOW_PHRASE = {
    "BOTH_BUYING":   "both FIIs and domestic institutions are buying — a bullish flow setup",
    "FII_BUYING":    "FIIs are net buyers, supporting the rally",
    "DII_ABSORBING": "FIIs are selling but domestic institutions are absorbing the supply",
    "FII_SELLING":   "FIIs are selling without strong domestic support — caution warranted",
    "NEUTRAL":       "institutional flows are mixed",
    "NO_DATA":       "flow data is unavailable today",
}

_REGIME_PHRASE = {
    "BULL_TREND":   "a sustained uptrend with broad participation",
    "ROTATION":     "active sector rotation — leadership is shifting",
    "CHOP":         "a choppy, range-bound tape — selectivity matters",
    "BEAR_TREND":   "a downtrend with narrow breadth — capital preservation mode",
    "UNKNOWN":      "an undefined regime",
}


def _greeting(now: datetime | None = None) -> str:
    """Time-of-day greeting based on local hour. India trading hours: 09:15 – 15:30 IST."""
    h = (now or datetime.now()).hour
    if 4 <= h < 12:
        return "Good morning"
    if 12 <= h < 17:
        return "Good afternoon"
    return "Good evening"


def _fmt_inr_crore(value: float) -> str:
    """Format INR crores with sign and direction word."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "no flow"
    direction = "net buyers of" if v > 0 else "net sellers of"
    return f"{direction} {abs(v):,.0f} crores"


# PG-voice: humanise the company-name field for natural narration.
# CSV stores names like "COAL INDIA LTD", "ADANI TOTAL GAS LIMITED", "CHENNAI PETROLEUM CORP LT".
# We want "Coal India", "Adani Total Gas", "Chennai Petroleum".
_COMPANY_SUFFIXES = (
    " LIMITED", " LTD.", " LTD", " LT", " CORP.", " CORP", " CORPORATION",
    " CO.", " CO", " PVT", " PRIVATE", " INDIA LTD", " THE ",
)


def _humanize_company(raw: str | None, fallback_symbol: str = "") -> str:
    """Convert ALL-CAPS company strings into natural Title Case for TTS."""
    if not raw or not str(raw).strip():
        return fallback_symbol or "this name"
    name = str(raw).strip().upper()
    # Strip common corporate suffixes (one pass, longest-first match).
    for suffix in sorted(_COMPANY_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    # Title-case but keep short tokens (≤ 3 chars) uppercase if they look like acronyms.
    parts = []
    for tok in name.split():
        if len(tok) <= 3 and tok.isalpha() and tok in {"NTPC", "ONGC", "BPCL", "HPCL", "GAIL", "SBI", "HDFC", "ICICI", "LIC", "IOC", "REC", "PFC", "IRCTC", "IRFC", "ITC", "L&T"}:
            parts.append(tok)
        else:
            parts.append(tok.capitalize())
    cleaned = " ".join(parts).strip()
    return cleaned or (fallback_symbol or "this name")


# PG-voice: translate machine setup_class codes into spoken-English phrases.
_SETUP_PHRASE = {
    "LEADER_BREAKOUT": "a clean leader-breakout setup",
    "PULLBACK_TO_SUPPORT": "a textbook pullback into support",
    "MOMENTUM_CONTINUATION": "a momentum-continuation pattern",
    "BASE_BREAKOUT": "a base-breakout structure",
    "REVERSAL": "an early reversal setup",
    "NEUTRAL": "a constructive technical structure",
    "OVERSOLD_BOUNCE": "an oversold-bounce setup",
}


def _setup_phrase(setup_class: str | None) -> str:
    if not setup_class:
        return "a constructive setup"
    key = str(setup_class).strip().upper()
    return _SETUP_PHRASE.get(key, "a constructive setup")


# PG-voice: indices snapshot ─────────────────────────────────────
def _load_index_snapshot(date_str: str | None = None) -> list[dict]:
    """Return today's close + day change % for the headline indices.

    Reads `data/nse_index_data.csv` (NSE bhavcopy-style schema). If `date_str`
    is given, uses that row; otherwise the latest available. Computes change
    against PREVCLOSE.
    """
    if not INDEX_DATA.exists():
        return []
    try:
        df = pd.read_csv(INDEX_DATA)
    except Exception:
        return []
    if df.empty or "TIMESTAMP" not in df.columns or "SYMBOL" not in df.columns:
        return []

    df["TIMESTAMP"] = df["TIMESTAMP"].astype(str)
    target = date_str or df["TIMESTAMP"].max()
    # If the requested date isn't in the dataset (signals can run ahead of index file),
    # fall back to the latest row available <= target, else the very latest.
    available = sorted(df["TIMESTAMP"].unique())
    if target not in available:
        prior = [d for d in available if d <= target]
        target = prior[-1] if prior else available[-1]

    snap = df[df["TIMESTAMP"] == target]
    out: list[dict] = []
    for symbol, spoken in HEADLINE_INDICES:
        row = snap[snap["SYMBOL"].astype(str).str.lower() == symbol.lower()]
        if row.empty:
            continue
        r = row.iloc[0]
        try:
            close = float(r["CLOSE"])
            prev = float(r["PREVCLOSE"])
        except (TypeError, ValueError, KeyError):
            continue
        if prev <= 0:
            continue
        change_pct = (close - prev) / prev * 100.0
        out.append({
            "symbol": symbol,
            "spoken": spoken,
            "close": close,
            "change_pct": change_pct,
            "date": target,
        })
    return out


def _format_index_phrase(indices: list[dict]) -> str:
    """Convert the indices snapshot into a single analyst-style sentence."""
    if not indices:
        return ""
    parts: list[str] = []
    for ix in indices:
        verb = "added" if ix["change_pct"] > 0 else ("shed" if ix["change_pct"] < 0 else "was flat at")
        if ix["change_pct"] == 0:
            parts.append(f"{ix['spoken']} {verb} {ix['close']:,.0f}")
        else:
            parts.append(
                f"{ix['spoken']} {verb} {abs(ix['change_pct']):.2f} percent to close at {ix['close']:,.0f}"
            )
    # Choose a tone-setting opener based on the headline (Nifty 50).
    headline = next((i for i in indices if i["symbol"] == "Nifty 50"), indices[0])
    if headline["change_pct"] >= 0.5:
        opener = "On the index front, a constructive session"
    elif headline["change_pct"] <= -0.5:
        opener = "On the index front, a soft session"
    else:
        opener = "On the index front, a quiet, two-way session"
    if len(parts) == 1:
        return f"{opener}. {parts[0]}."
    return f"{opener}. {parts[0]}; " + "; ".join(parts[1:-1] + [f"and {parts[-1]}"]) + "."


# PG-voice: company description (LLM-cached) ─────────────────────
# Curated fallback for very common names so we never need a network call for the obvious ones.
_COMPANY_DESC_FALLBACK = {
    "RELIANCE":   "India's largest conglomerate, with interests in oil-to-chemicals, telecom through Jio, and retail",
    "TCS":        "India's largest IT services exporter",
    "INFY":       "a global IT services and consulting major",
    "HDFCBANK":   "India's largest private-sector lender",
    "ICICIBANK":  "a leading private-sector bank with a strong retail franchise",
    "SBIN":       "the country's largest public-sector bank",
    "ITC":        "a diversified F-M-C-G, hotels, paperboards and agri-business major",
    "LT":         "India's flagship engineering and construction conglomerate",
    "BHARTIARTL": "a top-three Indian telecom operator with a growing Africa franchise",
    "COALINDIA":  "the world's largest coal producer, dominating Indian thermal coal supply",
    "ONGC":       "India's largest crude oil and natural gas producer",
    "NTPC":       "India's largest power generation utility",
    "POWERGRID":  "operator of India's national electricity transmission network",
    "TATASTEEL":  "one of India's leading integrated steel producers",
    "HINDUNILVR": "India's largest fast-moving consumer-goods company",
    "ASIANPAINT": "India's dominant decorative paints manufacturer",
    "MARUTI":     "the country's largest passenger-vehicle maker",
    "AXISBANK":   "a top-four private-sector bank",
    "KOTAKBANK":  "a private-sector bank known for its conservative book",
    "ATGL":       "a city-gas distribution operator, joint venture between Adani and TotalEnergies",
}


def _load_desc_cache() -> dict:
    if not COMPANY_DESC_CACHE.exists():
        return {}
    try:
        import json
        return json.loads(COMPANY_DESC_CACHE.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _save_desc_cache(cache: dict) -> None:
    try:
        import json
        COMPANY_DESC_CACHE.parent.mkdir(parents=True, exist_ok=True)
        COMPANY_DESC_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _generic_desc(company: str, sector: str) -> str:
    """Last-ditch description when no cache hit and no API key."""
    sector = (sector or "").strip()
    if sector:
        return f"a player in the {sector} space"
    return "a listed Indian company"


def _llm_describe(symbol: str, company: str, sector: str) -> str | None:
    """Ask gpt-4o-mini for a one-line, spoken-friendly description.

    Returns None if no API key or any failure.
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("SHUNYAAI_OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
        prompt = (
            f"In ONE short spoken sentence (max 22 words, no markdown, no quotes, no preamble), "
            f"describe what the NSE-listed Indian company '{company}' (ticker {symbol}, sector "
            f"{sector or 'unknown'}) does. Start the sentence directly with a verb or a noun phrase. "
            f"Do NOT begin with the company name, do NOT begin with 'The company', and do NOT use a dash. "
            f"Use plain English suitable for a voice briefing. Examples of good output: "
            f"'manufactures precision components for defence and aerospace clients', "
            f"'operates a city-gas distribution network across western India', "
            f"'India's largest private-sector lender, with a strong retail franchise'."
        )
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_DESC_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=80,
        )
        text = (resp.choices[0].message.content or "").strip().strip('"').strip()
        # Strip trailing period; we'll add our own punctuation.
        if text.endswith("."):
            text = text[:-1]
        return text or None
    except Exception:
        return None


def _describe_company(symbol: str, company: str, sector: str) -> str:
    """Resolve a one-line spoken description, using cache → curated → LLM → generic."""
    sym_key = (symbol or "").strip().upper()
    cache = _load_desc_cache()
    if sym_key and sym_key in cache and cache[sym_key]:
        return cache[sym_key]
    if sym_key in _COMPANY_DESC_FALLBACK:
        cache[sym_key] = _COMPANY_DESC_FALLBACK[sym_key]
        _save_desc_cache(cache)
        return cache[sym_key]
    llm = _llm_describe(sym_key, company, sector)
    if llm:
        cache[sym_key] = llm
        _save_desc_cache(cache)
        return llm
    return _generic_desc(company, sector)


def build_script(
    signals: pd.DataFrame,
    regime: dict,
    flows: dict,
    today: str,
    now: datetime | None = None,
    indices: list[dict] | None = None,
) -> str:
    """Assemble a ~60-second narrated script.

    Style notes:
      - Short, punchy sentences — GPT TTS and macOS `say` both deliver
        better prosody on short sentences than on long em-dash chains.
      - Section breaks use double-newline so `_to_say_macros()` can insert pause directives.
      - Em-dashes ( — ) become natural mid-sentence pauses; ellipses ( … ) become longer ones.
    """
    sections: list[str] = []

    # ---- Opening: greeting + date ------------------------------------------------
    greet = _greeting(now)
    # PG-voice: tailor the "walk you through" clause to time-of-day for natural flow.
    h = (now or datetime.now()).hour
    if 4 <= h < 12:
        when_clause = "this morning"
    elif 12 <= h < 17:
        when_clause = "this afternoon"
    else:
        when_clause = "this evening"
    sections.append(
        f"{greet}, my friend. This is your N-S-E market briefing for {today} — "
        f"let me walk you through what I'm seeing on the desk {when_clause}."
    )

    # ---- Indices recap ----------------------------------------------------------
    # PG-voice: always start with how the headline indices closed — sets the tape.
    if indices:
        idx_phrase = _format_index_phrase(indices)
        if idx_phrase:
            sections.append(idx_phrase)

    # ---- Market regime ----------------------------------------------------------
    regime_label = str(regime.get("current_regime") or "").upper()
    if not regime_label and not signals.empty and "regime_at_issue" in signals.columns:
        regime_label = (
            str(signals["regime_at_issue"].mode().iloc[0])
            if not signals["regime_at_issue"].empty else "UNKNOWN"
        )
    confidence = float(regime.get("confidence", 0) or 0)
    duration = int(regime.get("regime_duration_days", 0) or 0)
    phrase = _REGIME_PHRASE.get(regime_label, _REGIME_PHRASE["UNKNOWN"])
    label_spoken = regime_label.replace("_", " ").lower()
    if confidence > 0:
        day_word = "day" if duration == 1 else "days"
        sections.append(
            f"Market regime — {label_spoken}. {phrase.capitalize()}. "
            f"{confidence*100:.0f} percent conviction, {duration} {day_word} running."
        )
    else:
        sections.append(f"Market regime — {label_spoken}. {phrase.capitalize()}.")

    # ---- Institutional flows ----------------------------------------------------
    if flows:
        signal = str(flows.get("flow_signal") or "NO_DATA").upper()
        fii5 = flows.get("fii_net_5d", 0)
        dii5 = flows.get("dii_net_5d", 0)
        flow_phrase = _FLOW_PHRASE.get(signal, _FLOW_PHRASE["NEUTRAL"])
        sections.append(
            f"On flows — FIIs are {_fmt_inr_crore(fii5)} over five sessions; "
            f"DIIs are {_fmt_inr_crore(dii5)}. {flow_phrase.capitalize()}."
        )

    # ---- Sector leadership (1 line) ---------------------------------------------
    if not signals.empty and "sector" in signals.columns:
        buys = signals[signals["signal"].astype(str).str.upper().isin(["BUY", "STRONG_BUY"])]
        if not buys.empty:
            top_sectors = buys["sector"].value_counts().head(2).index.tolist()
            if len(top_sectors) == 1:
                sections.append(f"On sector leadership — strength is concentrated in {top_sectors[0]}.")
            elif len(top_sectors) >= 2:
                sections.append(
                    f"On sector leadership — {top_sectors[0]} is leading, with {top_sectors[1]} right behind it."
                )

    # ---- Top pick (1 stock, concise) --------------------------------------------
    # PG-voice: 1 top pick only — keeps 60s target. Full list in /voice script or /report.
    if not signals.empty:
        df = signals.copy()
        df["investment_score"] = pd.to_numeric(df.get("investment_score"), errors="coerce")
        buys = df[df["signal"].astype(str).str.upper().isin(["BUY", "STRONG_BUY"])]
        top1 = buys.sort_values("investment_score", ascending=False).head(1)
        if not top1.empty:
            row = top1.iloc[0]
            sym = str(row.get("symbol", "")).strip() or "this stock"
            company = _humanize_company(row.get("company"), sym)
            sector = str(row.get("sector") or "").strip()
            setup_phrase = _setup_phrase(row.get("setup_class"))
            try:
                score = int(round(float(row.get("investment_score") or 0)))
            except (TypeError, ValueError):
                score = 0
            sector_clause = f" from the {sector} space" if sector else ""
            description = _describe_company(sym, company, sector)
            sections.append(
                f"My top pick today — {company}, ticker {sym}{sector_clause}. "
                f"{company} {description}. "
                f"Showing {setup_phrase}, scoring {score} on the model."
            )

    # ---- Watchlist breakout -----------------------------------------------------
    if not signals.empty and "action_bucket" in signals.columns:
        watch = signals[signals["action_bucket"].astype(str).str.upper().isin(["BREAKOUT_WATCH", "BUY_WATCH"])]
        if not watch.empty:
            watch = watch.copy()
            watch["investment_score"] = pd.to_numeric(watch.get("investment_score"), errors="coerce")
            top_watch = watch.sort_values("investment_score", ascending=False).iloc[0]
            sym = str(top_watch.get("symbol", "")).strip() or "the leader"
            company = _humanize_company(top_watch.get("company"), sym)
            watch_sector = str(top_watch.get("sector") or "").strip()
            # PG-voice: include a one-liner so listeners know what the watchlist name actually does.
            watch_desc = _describe_company(sym, company, watch_sector)
            r1 = top_watch.get("target_1") or top_watch.get("entry_high")
            try:
                r1_str = f"{float(r1):.0f} rupees"
            except (TypeError, ValueError):
                r1_str = "its key resistance"
            sections.append(
                f"And one for the watchlist — {company}, ticker {sym}. "
                f"Coiling just below {r1_str} — a clean breakout on volume and that becomes a fresh entry."
            )

    # ---- Sign-off ---------------------------------------------------------------
    sections.append(
        "That's my read for today. Remember — size your positions, honour your stops, "
        "and let the winners run. I'll see you tomorrow morning. Trade well, my friend."
    )

    # Sections joined with blank lines so `_to_say_macros` can insert breath pauses.
    return "\n\n".join(sections)


def _to_say_macros(script: str, rate: int = DEFAULT_MAC_RATE) -> str:
    """Convert a natural-language script into one with macOS `say` prosody markers.

    macOS `say` supports inline directives:
      [[rate N]]      — words per minute
      [[slnc N]]      — silence for N milliseconds
      [[emph +]]      — emphasize next word; [[emph -]] reset
      [[pbas N]]      — pitch base (40–80 typical)

    We:
      - prepend a global rate setting
      - replace section breaks ( \n\n ) with a 600 ms pause for breathing
      - replace em-dashes ( — ) with a 250 ms pause for natural mid-sentence flow
      - replace ellipses ( … ) with a 400 ms pause
    """
    out = script.replace("\n\n", " [[slnc 600]] ")
    out = out.replace("—", "[[slnc 250]],")
    out = out.replace("…", "[[slnc 400]]")
    # Slight pause after the greeting period for warmth.
    out = out.replace(". Here is your", ". [[slnc 350]] Here is your", 1)
    return f"[[rate {rate}]] {out}"


# ─────────────────────────────────────────────
# TTS backends (in priority order)
# ─────────────────────────────────────────────

def _tts_openai(script: str, out_path: Path, voice: str = DEFAULT_VOICE, model: str = DEFAULT_MODEL) -> bool:
    """OpenAI TTS → MP3. Returns True on success.

    Uses gpt-4o-mini-tts by default with `instructions` for natural delivery.
    Uses GPT TTS. If a non-GPT model is supplied via environment, the explicit
    model is tried first and `gpt-4o-mini-tts` is the only fallback.
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("SHUNYAAI_OPENAI_API_KEY")
    if not api_key:
        return False
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
    except Exception as exc:
        print(f"  OpenAI library missing ({type(exc).__name__}): {exc}")
        return False

    # PG-voice: keep this on GPT TTS; do not silently fall back to legacy tts-1.
    candidates: list[str] = []
    seen: set[str] = set()
    for m in (model, "gpt-4o-mini-tts"):
        if m and m not in seen:
            candidates.append(m)
            seen.add(m)

    last_err: Exception | None = None
    for m in candidates:
        try:
            kwargs: dict = {"model": m, "voice": voice, "input": script}
            kwargs["instructions"] = VOICE_INSTRUCTIONS
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                response.stream_to_file(str(out_path))
            if out_path.exists() and out_path.stat().st_size > 0:
                if m != model:
                    print(f"  OpenAI TTS: requested {model!r} unavailable; used {m!r} instead.")
                else:
                    print(f"  OpenAI TTS: model={m}, voice={voice}")
                return True
        except Exception as exc:
            last_err = exc
            # Try the next model only if this one is missing/forbidden.
            msg = str(exc).lower()
            if any(s in msg for s in ("not_found", "does not exist", "model_not_found", "unsupported", "invalid_model")):
                continue
            # Other errors (auth, network) won't be fixed by switching models.
            print(f"  OpenAI TTS failed ({type(exc).__name__}): {exc}")
            return False

    if last_err:
        print(f"  OpenAI TTS failed ({type(last_err).__name__}): {last_err}")
    return False


def _tts_macos_say(script: str, out_path: Path, voice: str = DEFAULT_MAC_VOICE) -> bool:
    """macOS `say` command → AIFF fallback. Always available on macOS.

    Pipes the script in with prosody markers (via `_to_say_macros`) so the audio
    has natural pauses, breathing, and pacing rather than robotic monotone.
    """
    if sys.platform != "darwin":
        return False
    try:
        import subprocess
        narrated = _to_say_macros(script)
        result = subprocess.run(
            ["say", "-v", voice, "-o", str(out_path), narrated],
            capture_output=True, text=True, timeout=180,
        )
        return result.returncode == 0 and out_path.exists()
    except Exception as exc:
        print(f"  macOS say failed ({type(exc).__name__}): {exc}")
        return False


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def generate_briefing(date_str: str | None = None, want_tts: bool = True) -> dict:
    """End-to-end: load data → build script → write txt + (optional) audio.

    Returns dict with paths and metadata.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    signals = _load_signals_for_date(date_str)
    if signals.empty:
        print(f"⚠  No signals found for {date_str or 'latest'}. Generating minimal briefing.")
        actual_date = date_str or datetime.now().strftime("%Y-%m-%d")
    else:
        actual_date = str(signals["date_issued"].iloc[0])

    regime = _load_regime()
    flows = _load_flows()
    # PG-voice: indices snapshot for the recap sentence near the top of the briefing.
    indices = _load_index_snapshot(actual_date)

    # Format date for narration: "9 May 2026" instead of "2026-05-09"
    try:
        spoken_date = datetime.strptime(actual_date, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        spoken_date = actual_date

    script = build_script(signals, regime, flows, spoken_date, indices=indices)

    txt_path = OUTPUT_DIR / f"briefing_{actual_date}.txt"
    txt_path.write_text(script, encoding="utf-8")
    print(f"  Script:   {txt_path}  ({len(script.split())} words, ~{len(script.split())/2.5:.0f}s)")

    audio_path: Path | None = None
    if want_tts:
        mp3_path = OUTPUT_DIR / f"briefing_{actual_date}.mp3"
        if _tts_openai(script, mp3_path):
            audio_path = mp3_path
            print(f"  Audio:    {mp3_path}  (OpenAI TTS)")
        else:
            aiff_path = OUTPUT_DIR / f"briefing_{actual_date}.aiff"
            if _tts_macos_say(script, aiff_path):
                audio_path = aiff_path
                print(f"  Audio:    {aiff_path}  (macOS say fallback)")
            else:
                print("  Audio:    skipped (no OPENAI_API_KEY and no macOS `say`).")

    return {
        "date": actual_date,
        "script_path": str(txt_path),
        "audio_path": str(audio_path) if audio_path else None,
        "word_count": len(script.split()),
        "script": script,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily NSE voice briefing.")
    parser.add_argument("--date", help="Date (YYYY-MM-DD). Defaults to latest in signal_log.csv.")
    parser.add_argument("--no-tts", action="store_true", help="Skip audio synthesis; write script only.")
    parser.add_argument("--print", action="store_true", help="Print the script to stdout.")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("Voice Briefing Generation")
    print(f"{'='*60}")

    result = generate_briefing(date_str=args.date, want_tts=not args.no_tts)

    if args.print:
        print(f"\n--- SCRIPT ({result['date']}) ---")
        print(result["script"])
        print("--- END ---\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
