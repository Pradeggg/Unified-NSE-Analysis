def run(context):
    # Fetch and compare latest dates from each required table.
    freshness_status = {}
    index_date = context.fetch_date('market.index_eod', 'trade_date')
    equity_date = context.fetch_date('market.equity_eod', 'trade_date')
    stage_date = context.fetch_date('scores.stage_snapshots', 'snapshot_date')
    freshness_status['index_eod'] = 'fresh' if index_date >= context.threshold_date() else 'stale'
    freshness_status['equity_eod'] = 'fresh' if equity_date >= context.threshold_date() else 'stale'
    freshness_status['stage_snapshots'] = 'fresh' if stage_date >= context.threshold_date() else 'stale'
    return freshness_status