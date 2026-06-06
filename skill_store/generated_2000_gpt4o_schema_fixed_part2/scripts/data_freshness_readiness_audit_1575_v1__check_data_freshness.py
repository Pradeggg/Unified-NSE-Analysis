def run(context):
    # Check freshness across tables and return status
    max_trade_date = context['trade_date']
    freshness_status = {}
    for table in ['market.index_eod', 'market.equity_eod', 'scores.stage_snapshots']:
        latest_date = get_latest_date(table)
        if (max_trade_date - latest_date).days > 1:
            freshness_status[table] = 'stale'
        else:
            freshness_status[table] = 'fresh'
    return freshness_status