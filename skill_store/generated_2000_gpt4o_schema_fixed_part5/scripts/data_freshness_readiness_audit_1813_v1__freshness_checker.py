def run(context):
    threshold_date = context['current_date'] - timedelta(days=1)
    freshness_status = {
        'index_freshness': context['max_date_market_index'] >= threshold_date,
        'equity_freshness': context['max_date_market_equity'] >= threshold_date,
        'stage_snapshot_freshness': context['max_date_stage_snapshots'] >= threshold_date
    }
    return freshness_status