from terminal import web_research
from tools.ingest_company_concalls import ingest_company_concalls


def test_dry_run_cleans_nul_from_symbol_at_function_boundary(monkeypatch):
    seen = []

    def scrape(symbol):
        seen.append(symbol)
        return {"concalls": [], "concalls_link": ""}

    monkeypatch.setattr(web_research, "scrape_screener_in", scrape)

    result = ingest_company_concalls(symbol="L\x00T", dry_run=True)

    assert seen == ["LT"]
    assert result["symbol"] == "LT"
