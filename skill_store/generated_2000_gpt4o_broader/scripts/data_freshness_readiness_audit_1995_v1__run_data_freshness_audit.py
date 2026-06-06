def run(context):
    today = context['current_date']
    equity_freshness = (today - context['latest_equity_date']).days <= 1
    index_freshness = (today - context['latest_index_date']).days <= 1
    if equity_freshness and index_freshness:
        status = 'All data sources are fresh.'
    else:
        status = 'Some data sources are stale.'
    return {'status': status, 'details': {'equity_freshness': equity_freshness, 'index_freshness': index_freshness}}