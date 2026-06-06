def run(context):
    trade_date = context['latest_trade_date']
    snapshot_date = context['latest_snapshot_date']
    # Check the difference between trade and snapshot dates for freshness metric
    return 'Data is fresh.' if trade_date == snapshot_date else 'Stale or inconsistent data detected.'