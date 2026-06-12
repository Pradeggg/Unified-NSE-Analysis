from broker_research.sources import BROKER_SOURCES, BrokerSource, active_public_sources


def test_seeded_broker_sources_cover_user_supplied_public_sources():
    broker_codes = {source.broker_code for source in BROKER_SOURCES}

    assert {"icici", "hdfc_hsie", "axis", "sharekhan", "trendlyne"} <= broker_codes


def test_source_rows_are_stable_and_insertable():
    source = BrokerSource(
        broker_code="test",
        broker_name="Test Broker",
        source_kind="index_page",
        source_url="https://example.com/research",
        access_mode="public",
        url_pattern="",
        notes="fixture",
    )

    assert source.as_insert_params() == (
        "test",
        "Test Broker",
        "index_page",
        "https://example.com/research",
        "public",
        "",
        True,
        "fixture",
    )


def test_active_public_sources_excludes_login_required_rows():
    sources = active_public_sources()

    assert all(source.is_active for source in sources)
    assert all(source.access_mode in {"public", "partial"} for source in sources)
    assert not any(source.access_mode == "login_required" for source in sources)
