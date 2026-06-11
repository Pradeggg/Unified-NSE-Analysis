import nse_agent


def test_shared_command_registry_exposes_inventory_snapshot():
    registry = nse_agent._get_shared_registry()

    snapshot = registry.snapshot()

    assert snapshot[0]["name"] == "help"
    assert snapshot[0]["modes"] == ["interactive", "single_query"]
    assert "description" in snapshot[0]
    assert {row["name"] for row in snapshot} >= {
        "help",
        "commands",
        "scan",
        "council",
        "backtest",
        "open-last-report",
        "visual-scan",
        "doctor",
        "mtf",
        "strength",
        "email",
        "interaction",
        "quality-breakouts",
        "my-portfolio",
    }

