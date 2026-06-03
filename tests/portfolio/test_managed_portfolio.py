from __future__ import annotations

from pathlib import Path

import pytest

from portfolio.engine.managed_portfolio import ManagedPortfolioPolicy, load_policy


def test_load_policy_reads_default_yaml():
    policy = load_policy(Path("portfolio/config/portfolio_policy.yaml"))

    assert policy.start_date == "2025-01-01"
    assert policy.initial_capital == 1_000_000
    assert policy.max_single_stock_pct == 10
    assert policy.max_sector_pct == 25
    assert policy.risk_per_new_position_pct == 1.0
    assert policy.max_portfolio_open_risk_pct == 8


def test_policy_validation_rejects_invalid_risk():
    with pytest.raises(ValueError, match="risk_per_new_position_pct"):
        ManagedPortfolioPolicy(risk_per_new_position_pct=0)
