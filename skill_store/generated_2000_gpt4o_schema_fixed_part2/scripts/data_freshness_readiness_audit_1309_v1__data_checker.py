def run(context):
    max_eod_date = context['sql_executor'].exec('SELECT MAX(trade_date) FROM market.equity_eod;')['max']
    return {'eod_max_date': max_eod_date}