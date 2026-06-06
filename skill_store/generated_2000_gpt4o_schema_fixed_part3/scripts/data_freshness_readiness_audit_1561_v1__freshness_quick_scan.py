def run(context):
    # Evaluate freshness by comparing latest dates with current date
    freshness_status = {
        'equity_eod_fresh': context['latest_trade_date'] == context['current_date'],
        'index_eod_fresh': context['latest_index_date'] == context['current_date'],
        'stage_snapshot_fresh': context['latest_stage_date'] == context['current_date']
    }
    return freshness_status