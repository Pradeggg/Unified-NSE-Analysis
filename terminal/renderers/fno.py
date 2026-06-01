"""Renderer for the fno_overview intent."""

from terminal.renderers._base import _get, _source_trail_lines, FOOTER


def _fmt_num(value, decimals: int = 2) -> str:
    if isinstance(value, (int, float)):
        return f"{value:,.{decimals}f}"
    return "—"


def _fmt_int(value) -> str:
    if isinstance(value, (int, float)):
        return f"{int(value):,}"
    return "—"


def _fmt_oi_rows_simple(rows, side: str) -> str:
    """Format OI rows for the fno_chain / fno_futures fallback block."""
    if not rows:
        return "—"
    oi_key = "oi" if "oi" in rows[0] else ("ce_oi" if side == "CE" else "pe_oi")
    chg_key = "chg_oi" if "chg_oi" in rows[0] else ("ce_oi_chg" if side == "CE" else "pe_oi_chg")
    top = sorted(rows, key=lambda row: row.get(oi_key) or 0, reverse=True)[:5]
    parts = []
    for row in top:
        strike = row.get("strike", "—")
        oi = _fmt_int(row.get(oi_key))
        chg = row.get(chg_key)
        chg_txt = f", chg {int(chg):+,}" if isinstance(chg, (int, float)) else ""
        parts.append(f"{strike}: OI {oi}{chg_txt}")
    return " | ".join(parts)


def render(tool_results: list[dict]) -> str:
    """Render the fno_overview intent (and fno_chain/fno_futures fallback)."""
    fno_overview = _get(tool_results, "get_fno_overview")
    fno_chain = _get(tool_results, "get_options_chain") or _get(tool_results, "get_option_chain")
    fno_futures = _get(tool_results, "get_futures_analysis")
    fno_strategy = _get(tool_results, "get_strategy_recommendations")

    lines: list[str] = []

    # ── Primary: structured fno_overview result ──────────────────────────────
    if fno_overview:
        def _fmt_oi_rows_overview(rows, side=None) -> str:
            parts: list[str] = []
            for row in (rows or [])[:5]:
                strike = row.get("strike", "—")
                oi = next(
                    (row.get(k) for k in ("oi", "ce_oi", "pe_oi", "open_interest") if row.get(k) is not None),
                    None,
                )
                chg = next(
                    (row.get(k) for k in ("chg_oi", "ce_oi_chg", "pe_oi_chg", "oi_change") if row.get(k) is not None),
                    None,
                )
                oi_text = f"{int(oi):,}" if isinstance(oi, (int, float)) else str(oi or "—")
                chg_text = ""
                if isinstance(chg, (int, float)):
                    chg_text = f", chg {int(chg):+,}"
                parts.append(f"{strike} (OI {oi_text}{chg_text})")
            return "; ".join(parts) if parts else "—"

        symbol = fno_overview.get("symbol") or "NIFTY"
        lines.append(f"━━━ {symbol} — F&O Overview ━━━")
        lines.append("\n▶ OPTION CHAIN")
        chain = fno_overview.get("option_chain") or {}
        if chain.get("status") == "missing" or chain.get("error"):
            lines.append(f"  ERROR: {chain.get('error') or 'option-chain evidence missing'}")
        else:
            lines.append(
                f"  PCR: {fno_overview.get('pcr', '—')} | Max pain: {fno_overview.get('max_pain', '—')}"
            )
            top_oi = fno_overview.get("top_oi_strikes") or {}
            lines.append(f"  Top call OI: {_fmt_oi_rows_overview(top_oi.get('calls'))}")
            lines.append(f"  Top put OI: {_fmt_oi_rows_overview(top_oi.get('puts'))}")
        lines.append("\n▶ FUTURES BASIS & CARRY")
        futures = fno_overview.get("futures") or {}
        if futures.get("status") == "missing" or futures.get("error"):
            lines.append(f"  ERROR: {futures.get('error') or 'futures evidence missing'}")
        else:
            lines.append(
                f"  Basis: {fno_overview.get('basis', '—')} | "
                f"Cost of carry: {fno_overview.get('cost_of_carry', '—')}"
            )
        rec = fno_overview.get("recommendation") or {}
        lines.append("\n▶ STRATEGY CONTEXT")
        if rec.get("status") == "blocked":
            lines.append(f"  Blocked: {rec.get('reason')}")
        else:
            lines.append(f"  Strategy: {rec.get('strategy', '—')}")
            if rec.get("conditions"):
                lines.append("  Conditions: " + " | ".join(map(str, rec.get("conditions") or [])))
            if rec.get("invalidation"):
                lines.append(f"  Invalidation: {rec.get('invalidation')}")
            if rec.get("max_loss"):
                lines.append(f"  Max loss: {rec.get('max_loss')}")
            if rec.get("max_profit"):
                lines.append(f"  Max profit: {rec.get('max_profit')}")
        missing = fno_overview.get("missing_evidence") or []
        if missing:
            lines.append("\n▶ MISSING EVIDENCE")
            lines.append("  " + ", ".join(missing))
        lines.append("\n▶ SOURCE TRAIL")
        for tool, status in (fno_overview.get("source_trail") or {}).items():
            lines.append(f"  {tool}: {status}")
        lines.append(f"\n{FOOTER}")
        return "\n".join(l for l in lines if str(l).strip() != "")

    # ── Fallback: raw fno_chain / fno_futures / fno_strategy ─────────────────
    if fno_chain or fno_futures or fno_strategy:
        symbol = (
            (fno_chain or {}).get("symbol")
            or (fno_futures or {}).get("symbol")
            or (fno_strategy or {}).get("symbol")
            or "NIFTY"
        )
        lines.append(f"━━━ {symbol} — F&O Overview ━━━")

        if fno_chain and not fno_chain.get("error"):
            pcr = fno_chain.get("pcr")
            if isinstance(pcr, dict):
                pcr_text = (
                    f"OI {pcr.get('oi', '—')} | Volume {pcr.get('volume', '—')} | {pcr.get('signal', '—')}"
                )
            else:
                pcr_text = str(pcr if pcr is not None else "—")
            lines.append("\n▶ OPTION CHAIN")
            lines.append(
                f"  Expiry: {fno_chain.get('expiry', '—')} | "
                f"Spot/underlying: {_fmt_num(fno_chain.get('underlying'))} | "
                f"ATM: {fno_chain.get('atm', '—')} | "
                f"Source: {fno_chain.get('source', 'NSE live/API fallback')} | "
                f"As of: {fno_chain.get('as_of', '—')}"
            )
            lines.append(f"  PCR: {pcr_text} | Max pain: {fno_chain.get('max_pain', '—')}")
            if fno_chain.get("total_call_oi") is not None or fno_chain.get("total_put_oi") is not None:
                lines.append(
                    f"  Total OI: Calls {_fmt_int(fno_chain.get('total_call_oi'))} | "
                    f"Puts {_fmt_int(fno_chain.get('total_put_oi'))}"
                )
            calls = fno_chain.get("calls") or fno_chain.get("top_ce_oi_strikes") or []
            puts = fno_chain.get("puts") or fno_chain.get("top_pe_oi_strikes") or []
            lines.append(f"  Top CE OI / resistance zones: {_fmt_oi_rows_simple(calls, 'CE')}")
            lines.append(f"  Top PE OI / support zones: {_fmt_oi_rows_simple(puts, 'PE')}")
            if fno_chain.get("max_pain_vs_spot") is not None:
                lines.append(f"  Max pain vs spot: {_fmt_num(fno_chain.get('max_pain_vs_spot'))}")
        elif fno_chain:
            lines.append(f"\n▶ OPTION CHAIN\n  ERROR: {fno_chain.get('error')}")

        if fno_futures and not fno_futures.get("error"):
            lines.append("\n▶ FUTURES BASIS & CARRY")
            lines.append(
                f"  Spot: {_fmt_num(fno_futures.get('spot'))} | "
                f"Lot size: {fno_futures.get('lot_size', '—')} | "
                f"Source: {fno_futures.get('source', '—')} | As of: {fno_futures.get('as_of', '—')}"
            )
            for fut in (fno_futures.get("futures") or [])[:3]:
                lines.append(
                    f"  - Expiry {fut.get('expiry', '—')}: "
                    f"future {_fmt_num(fut.get('last_price') or fut.get('settle_price'))} | "
                    f"basis {_fmt_num(fut.get('basis'))} ({_fmt_num(fut.get('basis_pct'), 3)}%) | "
                    f"CoC {_fmt_num(fut.get('cost_of_carry_annualised_pct'))}% | "
                    f"OI {_fmt_int(fut.get('oi'))} | OI chg {_fmt_int(fut.get('oi_change'))}"
                )
            rollover = fno_futures.get("rollover") or {}
            if rollover:
                lines.append(
                    f"  Rollover: {rollover.get('rollover_pct', '—')}% | "
                    f"{rollover.get('interpretation', '—')}"
                )
        elif fno_futures:
            lines.append(f"\n▶ FUTURES BASIS & CARRY\n  ERROR: {fno_futures.get('error')}")

        if fno_strategy and not fno_strategy.get("error"):
            lines.append("\n▶ STRATEGY CONTEXT")
            lines.append(
                f"  IV regime: {fno_strategy.get('iv_regime', '—')} | "
                f"DTE: {fno_strategy.get('dte', '—')} | "
                f"PCR OI: {fno_strategy.get('pcr_oi', '—')} | "
                f"Max pain: {fno_strategy.get('max_pain', '—')}"
            )
            for rec in (fno_strategy.get("recommendations") or [])[:3]:
                name = rec.get("strategy") or rec.get("name") or rec.get("title") or "strategy"
                reason = rec.get("rationale") or rec.get("reason") or rec.get("why") or ""
                lines.append(f"  - {name}: {reason}".rstrip())
        elif fno_strategy:
            lines.append(f"\n▶ STRATEGY CONTEXT\n  ERROR: {fno_strategy.get('error')}")

        lines.append("\n▶ SOURCE TRAIL")
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
            lines.append(f"  {tr['tool']}: {status}")
        lines.append(f"\n{FOOTER}")
        return "\n".join(l for l in lines if str(l).strip() != "")

    # Nothing to render
    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)
