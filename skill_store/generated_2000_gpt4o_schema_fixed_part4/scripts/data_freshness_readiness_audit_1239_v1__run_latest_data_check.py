def run(context):
    return [
        {
            'symbol': record['symbol'],
            'freshness_metric': (context.today - record['trade_date']).days,
            'data_lag': record['close'] - context.base_close
        }
        for record in context.get_records()
    ]