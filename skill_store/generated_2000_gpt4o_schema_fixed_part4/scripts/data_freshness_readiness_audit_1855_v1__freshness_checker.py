def run(context):
    latest_index_date = context['latest_index_date']
    latest_equity_date = context['latest_equity_date']
    latest_snapshot_date = context['latest_snapshot_date']
    freshness_status = {
        'index_fresh': latest_index_date == context['current_date'],
        'equity_fresh': latest_equity_date == context['current_date'],
        'snapshot_fresh': latest_snapshot_date == context['current_date']
    }
    return freshness_status