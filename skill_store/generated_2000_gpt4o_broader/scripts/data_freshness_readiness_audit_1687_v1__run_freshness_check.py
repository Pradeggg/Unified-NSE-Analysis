def run(context):
    last_index_date = context['last_trade_date_index']
    last_equity_date = context['last_trade_date_equity']
    freshness_status = {}
    if last_index_date != last_equity_date:
        freshness_status['status'] = 'data mismatch'
    else:
        freshness_status['status'] = 'synced'
    return freshness_status