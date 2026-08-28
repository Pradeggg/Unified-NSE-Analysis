#!/usr/bin/env python3
"""Write a Cursor Canvas with Agent Adda price/SMA line charts.

Custom SVG candles often render blank in the canvas preview. This writer uses
only `cursor/canvas` primitives (LineChart, Stat, Pill) with data inlined.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]


def _chart_module():
    path = SCRIPT_DIR / "open_tradingview_chart.py"
    spec = importlib.util.spec_from_file_location("open_tradingview_chart", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cursor_canvas_dir(repo_root: Path | None = None) -> Path:
    """Return the Cursor-managed canvases folder for this repo."""
    root = (repo_root or PROJECT_ROOT).resolve()
    slug = str(root).lstrip("/").replace("/", "-")
    return Path.home() / ".cursor" / "projects" / slug / "canvases"


def _json_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return round(number, 4)


def _ffill(values: list[float | None]) -> list[float] | None:
    out: list[float] = []
    last: float | None = None
    for value in values:
        if value is None:
            if last is None:
                return None
            out.append(last)
        else:
            last = float(value)
            out.append(last)
    return out


def _tail_series(candles: list[dict[str, Any]], points: list[dict[str, Any]], count: int = 60) -> list[float] | None:
    by_time = {str(row.get("time")): row.get("value") for row in points or []}
    tail = candles[-count:]
    raw: list[float | None] = []
    for candle in tail:
        value = by_time.get(str(candle.get("time")))
        try:
            raw.append(float(value) if value is not None else None)
        except (TypeError, ValueError):
            raw.append(None)
    return _ffill(raw)


def pack_symbol(
    symbol: str,
    *,
    days: int = 60,
    include_snapshot: bool = True,
    include_intraday: bool = True,
    intra_interval: str = "5m",
) -> dict[str, Any]:
    chart = _chart_module()
    ticker = chart.canonical_symbol(symbol)
    snapshot = chart.load_snapshot(ticker) if include_snapshot else {"symbol": ticker}
    resolved = str(snapshot.get("resolved_symbol") or snapshot.get("symbol") or ticker)
    bars = chart.load_bars(resolved)
    payload = chart.build_payload(bars)
    candles = payload.get("candles") or []
    tail = candles[-days:]
    categories = [str(row["time"])[5:] for row in tail]
    closes = [round(float(row["close"]), 2) for row in tail]
    intra = chart.load_intraday_bars(resolved, intra_interval) if include_intraday else []
    intra_c = [round(float(row["close"]), 2) for row in intra]
    intra_h = [round(float(row["high"]), 2) for row in intra]
    intra_l = [round(float(row["low"]), 2) for row in intra]
    intra_o = [round(float(row["open"]), 2) for row in intra]
    from_open = None
    if intra_o and intra_c and intra_o[0]:
        from_open = round((intra_c[-1] / intra_o[0] - 1) * 100, 2)
    pack = {
        "symbol": resolved,
        "tv": chart.tradingview_symbol(resolved),
        "url": chart.tradingview_page_url(chart.tradingview_symbol(resolved), "D"),
        "url_5m": chart.tradingview_page_url(chart.tradingview_symbol(resolved), "5"),
        "price": _json_number(snapshot.get("price")),
        "rsi": _json_number(snapshot.get("rsi")),
        "supertrend": snapshot.get("supertrend") or payload.get("supertrend_state"),
        "sma20": _json_number(snapshot.get("sma20")),
        "sma50": _json_number(snapshot.get("sma50")),
        "sma200": _json_number(snapshot.get("sma200")),
        "as_of": snapshot.get("as_of"),
        "categories": categories,
        "close": closes,
        "sma20_line": _tail_series(candles, payload.get("sma20") or [], days),
        "sma50_line": _tail_series(candles, payload.get("sma50") or [], days),
        "sma200_line": _tail_series(candles, payload.get("sma200") or [], days),
        "bar_count": len(candles),
        "error": snapshot.get("error"),
        "intra_interval": (intra[0].get("interval") if intra else intra_interval) or "5m",
        "intra_t": [str(row["time"]) for row in intra],
        "intra_c": intra_c,
        "intra_h": intra_h,
        "intra_l": intra_l,
        "intra_high": max(intra_h) if intra_h else None,
        "intra_low": min(intra_l) if intra_l else None,
        "intra_last": intra_c[-1] if intra_c else None,
        "from_open": from_open,
    }
    return pack


def _tsx_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_canvas_tsx(packs: list[dict[str, Any]]) -> str:
    if not packs:
        raise ValueError("at least one symbol is required")
    template = r'''import {
  Callout,
  H1,
  H2,
  LineChart,
  Link,
  Pill,
  Row,
  Stack,
  Stat,
  Text,
  useCanvasState,
} from "cursor/canvas";

type StockPack = {
  symbol: string;
  tv: string;
  url: string;
  url_5m: string;
  price: number | null;
  rsi: number | null;
  supertrend: string | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  as_of: string | null;
  categories: string[];
  close: number[];
  sma20_line: number[] | null;
  sma50_line: number[] | null;
  sma200_line: number[] | null;
  bar_count: number;
  error: string | null;
  intra_interval: string;
  intra_t: string[];
  intra_c: number[];
  intra_h: number[];
  intra_l: number[];
  intra_high: number | null;
  intra_low: number | null;
  intra_last: number | null;
  from_open: number | null;
};

const STOCKS: StockPack[] = __STOCKS__;

function fmt(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function IntradayChart({ stock }: { stock: StockPack }) {
  if (!stock.intra_t.length) {
    return null;
  }
  const up = stock.intra_c[stock.intra_c.length - 1] >= stock.intra_c[0];
  return (
    <Stack gap={8}>
      <Text weight="semibold">
        {stock.tv} {stock.intra_interval} close · {stock.intra_t[0]}–{stock.intra_t[stock.intra_t.length - 1]} IST
      </Text>
      <LineChart
        categories={stock.intra_t}
        series={[
          { name: "Close (₹)", data: stock.intra_c, tone: up ? "success" : "danger" },
          { name: "High (₹)", data: stock.intra_h, tone: "info" },
          { name: "Low (₹)", data: stock.intra_l, tone: "warning" },
        ]}
        beginAtZero={false}
        fill
        height={240}
        valuePrefix="₹"
        showValues={stock.intra_c.length <= 12}
      />
      <Text size="small" tone="secondary">
        Source: Yahoo Finance {stock.intra_interval} NSE · Asia/Kolkata · session high {fmt(stock.intra_high)} · low {fmt(stock.intra_low)}
      </Text>
    </Stack>
  );
}

function DailyChart({ stock }: { stock: StockPack }) {
  const series: { name: string; data: number[]; tone?: "success" | "danger" | "info" | "warning" | "neutral" }[] = [
    {
      name: "Close (₹)",
      data: stock.close,
      tone: stock.close[stock.close.length - 1] >= stock.close[0] ? "success" : "danger",
    },
  ];
  if (stock.sma20_line) {
    series.push({ name: "SMA 20", data: stock.sma20_line, tone: "info" });
  }
  if (stock.sma50_line) {
    series.push({ name: "SMA 50", data: stock.sma50_line, tone: "warning" });
  }
  if (stock.sma200_line) {
    series.push({ name: "SMA 200", data: stock.sma200_line, tone: "neutral" });
  }
  return (
    <Stack gap={8}>
      <Text weight="semibold">{stock.tv} daily close with Agent Adda SMAs</Text>
      <LineChart
        categories={stock.categories}
        series={series}
        beginAtZero={false}
        fill
        height={280}
        valuePrefix="₹"
        showValues={false}
      />
      <Text size="small" tone="secondary">
        Source: local EOD via Agent Adda · last {stock.close.length} sessions · SMA 20/50/200 on close
      </Text>
    </Stack>
  );
}

export default function NseChartCanvas() {
  const [symbol, setSymbol] = useCanvasState("symbol", __DEFAULT__);
  const stock = STOCKS.find((row) => row.symbol === symbol) ?? STOCKS[0];
  const tone = stock.close[stock.close.length - 1] >= stock.close[0] ? "success" : "danger";
  const first = STOCKS[0];
  const second = STOCKS[1];
  const third = STOCKS[2];
  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>Agent Adda charts</H1>
        <Text tone="secondary">
          Intraday {stock.intra_interval} plus daily close/SMA 20/50/200. HTML from the skill script
          still has candles, RSI, MACD, and Supertrend. Research only.
        </Text>
      </Stack>
      <Callout tone="info" title="Open as a canvas">
        Open this file as a canvas beside chat, not as source. Custom SVG candles are not used here because they often render blank.
      </Callout>
      <Row gap={8} wrap>
        <Pill active={stock.symbol === first.symbol} onClick={() => setSymbol(first.symbol)}>
          {first.symbol}
        </Pill>
        {second ? (
          <Pill active={stock.symbol === second.symbol} onClick={() => setSymbol(second.symbol)}>
            {second.symbol}
          </Pill>
        ) : null}
        {third ? (
          <Pill active={stock.symbol === third.symbol} onClick={() => setSymbol(third.symbol)}>
            {third.symbol}
          </Pill>
        ) : null}
      </Row>
      <Row gap={16} wrap>
        <Stat value={fmt(stock.intra_last ?? stock.price ?? stock.close[stock.close.length - 1])} label={`${stock.symbol} last`} tone={tone} />
        <Stat value={stock.from_open === null || stock.from_open === undefined ? "—" : `${stock.from_open >= 0 ? "+" : ""}${fmt(stock.from_open)}%`} label="From open" tone={tone} />
        <Stat value={fmt(stock.intra_high)} label="Session high" />
        <Stat value={fmt(stock.intra_low)} label="Session low" />
        <Stat value={fmt(stock.sma20)} label="SMA 20" />
        <Stat value={fmt(stock.rsi)} label="RSI 14" />
      </Row>
      <H2>{stock.tv}</H2>
      <Text>
        As of {stock.as_of || "local EOD"}. {stock.bar_count} daily bars. Supertrend {stock.supertrend || "—"}.{" "}
        <Link href={stock.url_5m}>Open live TradingView 5m</Link>
        {" · "}
        <Link href={stock.url}>Daily</Link>
      </Text>
      {stock.intra_t.length ? <H2>Intraday</H2> : null}
      <IntradayChart stock={stock} />
      <H2>Daily</H2>
      <DailyChart stock={stock} />
    </Stack>
  );
}
'''
    return template.replace("__STOCKS__", _tsx_literal(packs)).replace(
        "__DEFAULT__", _tsx_literal(packs[0]["symbol"])
    )


def write_chart_canvas(
    symbols: list[str],
    *,
    output_path: Path | None = None,
    include_snapshot: bool = True,
    days: int = 60,
    include_intraday: bool = True,
    intra_interval: str = "5m",
) -> dict[str, Any]:
    tickers = [_chart_module().canonical_symbol(item) for item in symbols if str(item).strip()]
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        raise ValueError("symbol is required")
    packs = [
        pack_symbol(
            ticker,
            days=days,
            include_snapshot=include_snapshot,
            include_intraday=include_intraday,
            intra_interval=intra_interval,
        )
        for ticker in tickers
    ]
    tsx = render_canvas_tsx(packs)
    if output_path is None:
        slug = "-".join(ticker.lower() for ticker in tickers[:3])
        if len(tickers) > 3:
            slug += f"-plus{len(tickers) - 3}"
        output_path = cursor_canvas_dir() / f"{slug}-chart.canvas.tsx"
    destination = Path(output_path)
    if not destination.is_absolute():
        destination = PROJECT_ROOT / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(tsx, encoding="utf-8")
    return {
        "success": True,
        "symbols": [pack["symbol"] for pack in packs],
        "path": str(destination),
        "bar_counts": {pack["symbol"]: pack["bar_count"] for pack in packs},
        "intraday_bars": {pack["symbol"]: len(pack.get("intra_t") or []) for pack in packs},
        "note": "Open the .canvas.tsx as a canvas beside chat. Intraday pane is Yahoo 5m/15m; daily pane is local EOD SMAs.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+", help="NSE tickers (space or comma separated)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--intraday-interval", default="5m", help="5m or 15m")
    parser.add_argument("--no-intraday", action="store_true")
    parser.add_argument("--no-snapshot", action="store_true")
    args = parser.parse_args()
    raw: list[str] = []
    for item in args.symbols:
        raw.extend(part for part in re.split(r"[,\s]+", item) if part)
    try:
        result = write_chart_canvas(
            raw,
            output_path=args.output,
            include_snapshot=not args.no_snapshot,
            days=max(20, args.days),
            include_intraday=not args.no_intraday,
            intra_interval=args.intraday_interval,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
