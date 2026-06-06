def run(context):
    # Analyze data freshness using available dates.
    fresh_data_dates = context['market.index_eod']['trade_date']
    result = {'data_freshness': max(fresh_data_dates)}
    return result