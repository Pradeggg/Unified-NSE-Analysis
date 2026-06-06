def run(context):
    # Example function to compute data freshness
    latest_index = context['latest_index_date']
    latest_equity = context['latest_equity_date']
    latest_stage = context['latest_stage_date']
    latest_breadth = context['latest_breadth_date']
    return {
        'latest_dates': {
            'index_eod': latest_index,
            'equity_eod': latest_equity,
            'stage_snapshots': latest_stage,
            'market_daily': latest_breadth
        }
    }