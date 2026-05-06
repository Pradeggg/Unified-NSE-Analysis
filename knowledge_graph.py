#!/usr/bin/env python3
"""
knowledge_graph.py — NSE Knowledge Graph with Shock Propagation (P2-1)

Builds a lightweight in-memory graph of NSE stocks and their relationships:
  - index_peer:      stocks sharing the same sector/thematic index
  - promoter_group:  stocks under the same promoter conglomerate
  - supply_chain:    sector-level supply/demand links (steel→auto, etc.)

Exposes shock propagation: if stock X gets a SELL signal at -8%, compute
estimated impact on connected nodes.

Author: PG (Optimus) — P2-1
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
GRAPH_CACHE = ROOT / "data" / "nse_graph.json"
INDEX_MAP_CSV = ROOT / "data" / "index_stock_mapping.csv"

# ===== PROMOTER GROUP MAPPING =====
# PG: hand-curated conglomerate → stock mapping for major Indian groups.
# This covers top ~15 groups representing ~60% of Nifty 50 market cap.
# Stocks not in this map still get index_peer and supply_chain edges.
PROMOTER_GROUPS: dict[str, list[str]] = {
    "Tata": [
        "TCS", "TATASTEEL", "TATAMOTORS", "TATAPOWER", "TATACONSUM",
        "TATACOMM", "TATAELXSI", "TATACHEM", "TTML", "TITAN",
        "VOLTAS", "RALLIS", "IDFCFIRSTB", "TATATECH",
    ],
    "Reliance": [
        "RELIANCE", "JIOFIN",
    ],
    "Adani": [
        "ADANIENT", "ADANIPORTS", "ADANIGREEN", "ADANIPOWER",
        "ATGL", "AWL", "ADANIENSOL", "ADANIWILMAR", "NDTV",
    ],
    "Birla": [
        "GRASIM", "ULTRACEMCO", "HINDALCO", "IDEA", "ABCAPITAL",
        "ABFRL", "BIRLASOFT",
    ],
    "Mahindra": [
        "M&M", "TECHM", "MAHINDCIE", "MHRIL", "MAHLIFE",
    ],
    "Bajaj": [
        "BAJFINANCE", "BAJAJFINSV", "BAJAJAUTO", "BAJAJHLDNG",
    ],
    "L&T": [
        "LT", "LTIM", "LTTS", "LTTECHFIN",
    ],
    "HDFC": [
        "HDFCBANK", "HDFCLIFE", "HDFCAMC",
    ],
    "ICICI": [
        "ICICIBANK", "ICICIGI", "ICICIPRULI",
    ],
    "SBI": [
        "SBIN", "SBILIFE", "SBICARD",
    ],
    "Kotak": [
        "KOTAKBANK", "KOTAKMAHAMC",
    ],
    "Godrej": [
        "GODREJCP", "GODREJPROP", "GODREJIND", "GODREJAGRO",
    ],
    "JSW": [
        "JSWSTEEL", "JSWENERGY", "JSWINFRA", "JSPL",
    ],
    "Vedanta": [
        "VEDL", "HINDZINC",
    ],
    "Murugappa": [
        "TIINDIA", "CGPOWER", "CHOLAFIN", "CHOLAHLDNG",
    ],
    "Torrent": [
        "TORNTPHARM", "TORNTPOWER",
    ],
    "Sun": [
        "SUNPHARMA", "SPARC",
    ],
    "Cipla": [
        "CIPLA",
    ],
    "Hero": [
        "HEROMOTOCO",
    ],
    "TVS": [
        "TVSMOTOR", "TVSSCS",
    ],
    "Havells": [
        "HAVELLS", "LLOYDSENGG",
    ],
    "PI": [
        "PIIND",
    ],
    "Divi's": [
        "DIVISLAB",
    ],
}

# ===== SECTOR-LEVEL SUPPLY CHAIN LINKS =====
# PG: sector A → sector B means A is a supplier/input to B.
# Weight indicates strength of supply chain linkage (0.3 = moderate, 0.6 = strong).
SECTOR_SUPPLY_CHAIN: list[dict] = [
    # Metals → downstream
    {"from_sector": "Metal", "to_sector": "Auto", "weight": 0.5, "note": "steel/aluminium input"},
    {"from_sector": "Metal", "to_sector": "Capital Goods", "weight": 0.4, "note": "steel for engineering"},
    {"from_sector": "Metal", "to_sector": "Realty", "weight": 0.4, "note": "construction steel/cement"},
    {"from_sector": "Metal", "to_sector": "Infrastructure", "weight": 0.5, "note": "steel for infra projects"},
    # Energy → downstream
    {"from_sector": "Energy", "to_sector": "Chemical", "weight": 0.5, "note": "crude/gas feedstock"},
    {"from_sector": "Energy", "to_sector": "Auto", "weight": 0.3, "note": "fuel cost impact"},
    {"from_sector": "Energy", "to_sector": "FMCG", "weight": 0.2, "note": "packaging/transport cost"},
    # IT → enablers
    {"from_sector": "IT", "to_sector": "Banking & Finance", "weight": 0.3, "note": "tech services for BFSI"},
    # Banking → credit flow
    {"from_sector": "Banking & Finance", "to_sector": "Realty", "weight": 0.5, "note": "home loan credit"},
    {"from_sector": "Banking & Finance", "to_sector": "Auto", "weight": 0.4, "note": "auto loan credit"},
    {"from_sector": "Banking & Finance", "to_sector": "Capital Goods", "weight": 0.3, "note": "project finance"},
    # Pharma ↔ Healthcare
    {"from_sector": "Pharma", "to_sector": "Healthcare", "weight": 0.6, "note": "pharma supply to hospitals"},
    # Chemical → Agri
    {"from_sector": "Chemical", "to_sector": "FMCG", "weight": 0.3, "note": "agri-chemical for food chain"},
    # Cement → Realty/Infra
    {"from_sector": "Cement", "to_sector": "Realty", "weight": 0.5, "note": "cement for construction"},
    {"from_sector": "Cement", "to_sector": "Infrastructure", "weight": 0.5, "note": "cement for infra"},
    # Defence → PSU linkage
    {"from_sector": "Defence", "to_sector": "Capital Goods", "weight": 0.3, "note": "defence equipment orders"},
    # Telecom → IT convergence
    {"from_sector": "Telecom", "to_sector": "IT", "weight": 0.3, "note": "digital infra demand"},
    # Power → industrial demand
    {"from_sector": "Energy - Power", "to_sector": "Metal", "weight": 0.4, "note": "power for smelting"},
    {"from_sector": "Energy - Power", "to_sector": "Capital Goods", "weight": 0.3, "note": "power equipment"},
]

# PG: Sector name normalization — map index names to canonical sector names
# used in sector_rotation_report.py
SECTOR_INDEX_MAP: dict[str, str] = {
    "NIFTY BANK": "Banking & Finance",
    "NIFTY FINANCIAL SERVICES": "Banking & Finance",
    "NIFTY FINANCIAL SERVICES EX-BANK": "Banking & Finance",
    "NIFTY PRIVATE BANK": "Banking & Finance",
    "NIFTY PSU BANK": "Banking & Finance",
    "NIFTY AUTO": "Auto",
    "NIFTY IT": "IT",
    "NIFTY PHARMA": "Pharma",
    "NIFTY500 HEALTHCARE": "Healthcare",
    "NIFTY MIDSMALL HEALTHCARE": "Healthcare",
    "NIFTY REALTY": "Realty",
    "NIFTY ENERGY": "Energy",
    "NIFTY METAL": "Metal",
    "NIFTY MEDIA": "Media",
    "NIFTY FMCG": "FMCG",
    "NIFTY OIL & GAS": "Energy",
    "NIFTY COMMODITIES": None,  # skip — too heterogeneous (metals+oil+power+chem)
    "NIFTY CONSUMER DURABLES": "FMCG",
    "NIFTY INFRASTRUCTURE": "Infrastructure",
    "NIFTY INDIA DEFENCE": "Defence",
    "NIFTY HOUSING": "Realty",
    "NIFTY EV & NEW AGE AUTOMOTIVE": "Auto",
    "NIFTY INDIA MANUFACTURING": "Capital Goods",
    "NIFTY MNC": "MNC",
    "NIFTY CPSE": "PSU",
    "NIFTY PSE": "PSU",
    "NIFTY INDIA DIGITAL": "IT",
    "NIFTY MOBILITY": "Auto",
    "NIFTY TRANSPORTATION & LOGISTICS": "Infrastructure",
    "NIFTY RURAL": "FMCG",
    "NIFTY NON-CYCLICAL CONSUMER": "FMCG",
    "NIFTY INDIA SELECT 5 CORPORATE GROUPS (MAATR)": None,  # skip — conglomerate mix
    "NIFTY TOTAL MARKET": None,  # skip — too broad
    "NIFTY 50": None,
    "NIFTY 100": None,
    "NIFTY 200": None,
    "NIFTY 500": None,
    "NIFTY NEXT 50": None,
    "NIFTY MIDCAP 50": None,
    "NIFTY MIDCAP 100": None,
    "NIFTY MIDCAP 150": None,
    "NIFTY MICROCAP 250": None,
    "NIFTY LARGEMIDCAP 250": None,
    "NIFTY SMALLCAP 50": None,
    "NIFTY SMALLCAP 100": None,
    "NIFTY SMALLCAP 250": None,
    "Nifty Sme Emerge": None,
}

# ===== GRAPH DATA STRUCTURES =====

class Edge:
    __slots__ = ("source", "target", "edge_type", "weight", "note")

    def __init__(self, source: str, target: str, edge_type: str,
                 weight: float = 0.5, note: str = ""):
        self.source = source
        self.target = target
        self.edge_type = edge_type
        self.weight = weight
        self.note = note

    def to_dict(self) -> dict:
        return {
            "from": self.source, "to": self.target,
            "type": self.edge_type, "weight": self.weight, "note": self.note,
        }


class NSEGraph:
    """Lightweight in-memory knowledge graph for NSE stocks."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}          # symbol → attributes
        self.adj: dict[str, list[Edge]] = defaultdict(list)  # adjacency list
        self._group_map: dict[str, str] = {}       # symbol → promoter group name
        self._sector_map: dict[str, set[str]] = defaultdict(set)  # sector → symbols

    # ---- Node management ----

    def add_node(self, symbol: str, **attrs) -> None:
        self.nodes.setdefault(symbol, {}).update(attrs)

    def add_edge(self, source: str, target: str, edge_type: str,
                 weight: float = 0.5, note: str = "") -> None:
        """Add a directed edge (and reverse for undirected relationship types)."""
        e = Edge(source, target, edge_type, weight, note)
        self.adj[source].append(e)
        # Promoter group and sector peer edges are bidirectional
        if edge_type in ("promoter_group", "index_peer", "sector_peer"):
            self.adj[target].append(Edge(target, source, edge_type, weight, note))

    # ---- Graph construction ----

    def build_from_data(self,
                        index_map_csv: Path = INDEX_MAP_CSV,
                        analysis_df: pd.DataFrame | None = None) -> None:
        """Build graph from available NSE data sources."""
        # 1. Load index-stock mapping → index_peer edges + sector assignment
        if index_map_csv.exists():
            idx_df = pd.read_csv(index_map_csv)
            # Group stocks by sector index
            sector_stocks: dict[str, list[str]] = defaultdict(list)
            for _, row in idx_df.iterrows():
                idx_name = str(row.get("INDEX_NAME", ""))
                sym = str(row.get("STOCK_SYMBOL", "")).strip().upper()
                if not sym:
                    continue
                self.add_node(sym, type="stock")
                # Map to canonical sector
                canon_sector = SECTOR_INDEX_MAP.get(idx_name)
                if canon_sector is None:
                    # Skip broad market indices and explicitly excluded ones
                    if idx_name in SECTOR_INDEX_MAP:
                        continue
                    # Unknown index — skip if it looks like a broad market index
                    idx_upper = idx_name.upper()
                    if any(kw in idx_upper for kw in ("NIFTY 5", "NIFTY 1", "NIFTY 2", "MIDCAP", "SMALLCAP", "MICRO", "LARGE", "SME")):
                        continue
                    canon_sector = idx_name  # fallback: use raw index name
                self.nodes[sym]["sector"] = canon_sector
                self._sector_map[canon_sector].add(sym)
                sector_stocks[canon_sector].append(sym)

            # Create index_peer edges within each sector (cap to avoid combinatorial explosion)
            for sector, members in sector_stocks.items():
                if len(members) > 40:
                    continue  # skip overly broad groups
                for i, s1 in enumerate(members):
                    for s2 in members[i+1:]:
                        self.add_edge(s1, s2, "index_peer", weight=0.3,
                                      note=f"both in {sector}")

        # 2. Add analysis data as node attributes
        if analysis_df is not None and not analysis_df.empty:
            for _, row in analysis_df.iterrows():
                sym = str(row.get("SYMBOL", "")).strip().upper()
                if not sym:
                    continue
                self.add_node(
                    sym,
                    type="stock",
                    company_name=str(row.get("COMPANY_NAME", "")),
                    market_cap_cat=str(row.get("MARKET_CAP_CATEGORY", "")),
                )

        # 3. Promoter group edges
        for group_name, members in PROMOTER_GROUPS.items():
            for i, s1 in enumerate(members):
                self.add_node(s1, promoter_group=group_name)
                self._group_map[s1] = group_name
                for s2 in members[i+1:]:
                    self.add_edge(s1, s2, "promoter_group", weight=0.7,
                                  note=f"{group_name} group")

        # 4. Sector supply chain edges (aggregate: connect all stocks in source sector
        #    to all stocks in target sector would be too many; instead connect sectors as
        #    "virtual" supply chain — propagation uses sector membership lookup)
        self._supply_chain = SECTOR_SUPPLY_CHAIN  # stored for propagation

    # ---- Shock Propagation ----

    def propagate_shock(self, source_symbol: str, shock_pct: float,
                        depth: int = 2, min_impact: float = 0.5) -> dict[str, dict]:
        """BFS shock propagation from a stock through its graph connections.

        Returns: {symbol: {impact_pct, path, edge_type, note}}
        - impact decays by edge weight × 0.4 per hop (40% propagation factor)
        - min_impact filters out negligible impacts (default 0.5%)
        """
        PROPAGATION_FACTOR = 0.4
        results: dict[str, dict] = {}
        visited = {source_symbol}
        queue: list[tuple[str, float, int, str, str]] = [
            (source_symbol, shock_pct, 0, "", "")
        ]

        while queue:
            next_queue: list[tuple[str, float, int, str, str]] = []
            for node, impact, hops, path, via_type in queue:
                if hops >= depth:
                    continue
                # Direct graph edges
                for edge in self.adj.get(node, []):
                    target = edge.target
                    if target in visited:
                        continue
                    child_impact = impact * edge.weight * PROPAGATION_FACTOR
                    if abs(child_impact) < min_impact:
                        continue
                    visited.add(target)
                    new_path = f"{path} → {node}" if path else node
                    results[target] = {
                        "impact_pct": round(child_impact, 2),
                        "path": f"{new_path} → {target}",
                        "edge_type": edge.edge_type,
                        "note": edge.note,
                        "hops": hops + 1,
                    }
                    next_queue.append((target, child_impact, hops + 1,
                                       new_path, edge.edge_type))

                # Sector supply chain propagation
                node_sector = self.nodes.get(node, {}).get("sector", "")
                if node_sector:
                    for sc in self._supply_chain:
                        linked_sector = None
                        direction = ""
                        if sc["from_sector"] == node_sector:
                            linked_sector = sc["to_sector"]
                            direction = "downstream"
                        elif sc["to_sector"] == node_sector:
                            linked_sector = sc["from_sector"]
                            direction = "upstream"
                        if not linked_sector:
                            continue
                        sc_weight = sc["weight"]
                        for target in list(self._sector_map.get(linked_sector, set()))[:10]:
                            # Cap to 10 per sector to limit explosion
                            if target in visited:
                                continue
                            child_impact = impact * sc_weight * PROPAGATION_FACTOR * 0.5
                            # Extra 0.5 discount for sector-level (less direct)
                            if abs(child_impact) < min_impact:
                                continue
                            visited.add(target)
                            new_path = f"{path} → {node}" if path else node
                            results[target] = {
                                "impact_pct": round(child_impact, 2),
                                "path": f"{new_path} →({linked_sector})→ {target}",
                                "edge_type": "supply_chain",
                                "note": f"{direction}: {sc['note']}",
                                "hops": hops + 1,
                            }
                            next_queue.append((target, child_impact, hops + 1,
                                               new_path, "supply_chain"))

            queue = next_queue

        return results

    # ---- Query helpers ----

    def get_group(self, symbol: str) -> str:
        """Return the promoter group name for a symbol, or ''."""
        return self._group_map.get(symbol, "")

    def get_peers(self, symbol: str, edge_type: str | None = None) -> list[str]:
        """Return all directly connected symbols, optionally filtered by edge type."""
        peers = []
        for edge in self.adj.get(symbol, []):
            if edge_type and edge.edge_type != edge_type:
                continue
            peers.append(edge.target)
        return peers

    def get_sector(self, symbol: str) -> str:
        return self.nodes.get(symbol, {}).get("sector", "")

    def summary(self) -> dict:
        n_nodes = len(self.nodes)
        n_edges = sum(len(v) for v in self.adj.values())
        n_groups = len(set(self._group_map.values()))
        n_sectors = len(self._sector_map)
        return {
            "nodes": n_nodes,
            "edges": n_edges,
            "promoter_groups": n_groups,
            "sectors": n_sectors,
        }

    # ---- Serialization ----

    def save(self, path: Path = GRAPH_CACHE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": self.nodes,
            "edges": [e.to_dict() for edges in self.adj.values() for e in edges],
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = GRAPH_CACHE) -> "NSEGraph":
        g = cls()
        if not path.exists():
            return g
        data = json.loads(path.read_text(encoding="utf-8"))
        g.nodes = data.get("nodes", {})
        for e in data.get("edges", []):
            g.add_edge(e["from"], e["to"], e["type"], e.get("weight", 0.5), e.get("note", ""))
        # Rebuild internal lookups
        for sym, attrs in g.nodes.items():
            grp = attrs.get("promoter_group", "")
            if grp:
                g._group_map[sym] = grp
            sec = attrs.get("sector", "")
            if sec:
                g._sector_map[sec].add(sym)
        g._supply_chain = SECTOR_SUPPLY_CHAIN
        return g


# ===== SINGLETON GRAPH INSTANCE =====

_GRAPH: NSEGraph | None = None


def get_graph(analysis_df: pd.DataFrame | None = None, force_rebuild: bool = False) -> NSEGraph:
    """Get or build the singleton graph instance."""
    global _GRAPH
    if _GRAPH is not None and not force_rebuild:
        return _GRAPH
    # Try loading from cache first
    if GRAPH_CACHE.exists() and not force_rebuild:
        _GRAPH = NSEGraph.load(GRAPH_CACHE)
        if _GRAPH.nodes:
            return _GRAPH
    # Build fresh
    _GRAPH = NSEGraph()
    _GRAPH.build_from_data(analysis_df=analysis_df)
    _GRAPH.save()
    return _GRAPH


# ===== INTEGRATION API (called from sector_rotation_report.py) =====

def enrich_with_graph_signals(candidates: pd.DataFrame,
                               analysis_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add GRAPH_SIGNAL and GRAPH_DETAIL columns to candidates DataFrame.

    Logic: for each candidate with a SELL or BUY signal, propagate through the graph
    and tag other candidates that are downstream/upstream.
    """
    df = candidates.copy()
    df["GRAPH_SIGNAL"] = ""
    df["GRAPH_DETAIL"] = ""

    graph = get_graph(analysis_df=analysis_df)
    if not graph.nodes:
        return df

    candidate_syms = set(df["SYMBOL"].dropna().tolist())

    # Collect all shocks from candidates with BUY/SELL signals
    shock_results: dict[str, list[dict]] = defaultdict(list)

    for _, row in df.iterrows():
        sym = str(row.get("SYMBOL", ""))
        signal = str(row.get("TRADING_SIGNAL", "HOLD")).upper()
        score = float(row.get("INVESTMENT_SCORE", 50) or 50)

        # Only propagate meaningful signals
        if signal == "BUY" and score >= 65:
            shock_pct = +(score - 50) * 0.15  # ~+2 to +4% implied positive shock
        elif signal == "SELL":
            shock_pct = -(100 - score) * 0.15  # ~-3 to -7% implied negative shock
        elif signal == "HOLD" and score < 35:
            shock_pct = -(50 - score) * 0.10  # weak HOLD = mild negative
        else:
            continue

        impacts = graph.propagate_shock(sym, shock_pct, depth=2, min_impact=0.3)
        for target, info in impacts.items():
            if target in candidate_syms and target != sym:
                shock_results[target].append({
                    "source": sym,
                    "impact_pct": info["impact_pct"],
                    "edge_type": info["edge_type"],
                    "note": info["note"],
                    "hops": info["hops"],
                })

    # Aggregate shocks per target
    for sym, shocks in shock_results.items():
        if not shocks:
            continue
        net_impact = sum(s["impact_pct"] for s in shocks)
        top_shock = max(shocks, key=lambda s: abs(s["impact_pct"]))

        if net_impact > 1.0:
            signal_label = "BENEFICIARY"
        elif net_impact < -1.0:
            signal_label = "AT_RISK"
        else:
            signal_label = "WATCH"

        detail_parts = []
        for s in sorted(shocks, key=lambda x: abs(x["impact_pct"]), reverse=True)[:3]:
            direction = "+" if s["impact_pct"] > 0 else ""
            detail_parts.append(
                f"{s['source']}({direction}{s['impact_pct']:.1f}% via {s['edge_type']})"
            )

        mask = df["SYMBOL"] == sym
        df.loc[mask, "GRAPH_SIGNAL"] = signal_label
        df.loc[mask, "GRAPH_DETAIL"] = "; ".join(detail_parts)

    n_tagged = (df["GRAPH_SIGNAL"] != "").sum()
    print(f"  Knowledge graph: {len(graph.nodes)} nodes, {n_tagged} candidates tagged with graph signals.")
    return df


def graph_context_for_llm(candidates: pd.DataFrame) -> str:
    """Build a compact graph context string for the LLM narrative prompt."""
    tagged = candidates[candidates["GRAPH_SIGNAL"].notna() & (candidates["GRAPH_SIGNAL"] != "")]
    if tagged.empty:
        return ""
    lines = []
    for _, row in tagged.iterrows():
        sym = row["SYMBOL"]
        sig = row["GRAPH_SIGNAL"]
        det = row.get("GRAPH_DETAIL", "")
        lines.append(f"  {sym}: {sig} — {det}")
    return "Knowledge graph cross-impact signals:\n" + "\n".join(lines)


# PG: CSS for graph signal badges in HTML
GRAPH_CSS = """
/* P2-1: Knowledge graph signal badges */
.gs-badge{display:inline-block;padding:2px 6px;border-radius:8px;font-size:10px;font-weight:600}
.gs-ben{background:#dcfce7;color:#166534}
.gs-risk{background:#fee2e2;color:#991b1b}
.gs-watch{background:#fef9c3;color:#854d0e}
"""


def graph_signal_badge(signal: str, detail: str = "") -> str:
    """Return an HTML badge for the graph signal."""
    if not signal or signal in ("", "nan", "None"):
        return ""
    cls_map = {"BENEFICIARY": "gs-ben", "AT_RISK": "gs-risk", "WATCH": "gs-watch"}
    label_map = {"BENEFICIARY": "🟢 Beneficiary", "AT_RISK": "🔴 At Risk", "WATCH": "🟡 Watch"}
    cls = cls_map.get(signal, "gs-watch")
    lbl = label_map.get(signal, signal)
    title = f' title="{detail}"' if detail else ""
    return f'<span class="gs-badge {cls}"{title}>{lbl}</span>'


# ===== CLI for testing =====

if __name__ == "__main__":
    print("=" * 60)
    print("NSE Knowledge Graph — P2-1")
    print("=" * 60)

    # Build graph
    try:
        analysis = pd.read_csv(
            sorted(
                (ROOT / "reports").rglob("comprehensive_nse_enhanced_*.csv"),
                key=lambda p: p.stat().st_mtime, reverse=True
            )[0]
        )
    except Exception:
        analysis = None

    graph = get_graph(analysis_df=analysis, force_rebuild=True)
    s = graph.summary()
    print(f"  Nodes: {s['nodes']}")
    print(f"  Edges: {s['edges']}")
    print(f"  Promoter groups: {s['promoter_groups']}")
    print(f"  Sectors: {s['sectors']}")

    # Test shock propagation
    print("\n--- Shock Test: TATASTEEL SELL (-8%) ---")
    impacts = graph.propagate_shock("TATASTEEL", -8.0, depth=2, min_impact=0.3)
    for sym, info in sorted(impacts.items(), key=lambda x: abs(x[1]["impact_pct"]), reverse=True)[:15]:
        print(f"  {sym:20s}  {info['impact_pct']:+.2f}%  ({info['edge_type']}: {info['note']})")

    print("\n--- Shock Test: RELIANCE BUY (+5%) ---")
    impacts = graph.propagate_shock("RELIANCE", +5.0, depth=2, min_impact=0.3)
    for sym, info in sorted(impacts.items(), key=lambda x: abs(x[1]["impact_pct"]), reverse=True)[:10]:
        print(f"  {sym:20s}  {info['impact_pct']:+.2f}%  ({info['edge_type']}: {info['note']})")

    print("\n--- Promoter Group Lookup ---")
    for test_sym in ["TCS", "ADANIENT", "HDFCBANK", "RELIANCE", "INFY"]:
        grp = graph.get_group(test_sym)
        print(f"  {test_sym}: {grp or '(none)'}")

    print(f"\nGraph saved to {GRAPH_CACHE}")
