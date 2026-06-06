def run(context):
    freshness_health = {
        'index': context['latest_index_date'],
        'equity': context['latest_equity_date'],
        'stage': context['latest_stage_date'],
        'market_daily': context['latest_market_daily_date']
    }
    return freshness_health