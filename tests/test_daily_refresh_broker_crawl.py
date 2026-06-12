import daily_refresh


def test_step_broker_research_crawl_respects_dry_run(capsys):
    assert daily_refresh.step_broker_research_crawl("BEL", dry_run=True, max_sources=2)

    output = capsys.readouterr().out
    assert "Broker Research Crawl" in output
    assert "[DRY RUN" in output


def test_step_broker_research_crawl_uses_injected_runner(capsys):
    calls = []

    class Result:
        symbol = "BEL"
        sources_seen = 2
        sources_succeeded = 2
        sources_failed = 0
        links_discovered = 4
        reports_stored = 3
        skipped_sources = 1
        failures = []

    def runner(**kwargs):
        calls.append(kwargs)
        return Result()

    assert daily_refresh.step_broker_research_crawl("BEL", dry_run=False, max_sources=2, runner=runner, conn=object())

    output = capsys.readouterr().out
    assert calls[0]["symbol"] == "BEL"
    assert calls[0]["max_sources"] == 2
    assert "Reports stored: 3" in output
