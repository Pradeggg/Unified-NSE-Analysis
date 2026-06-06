def run(context):
    # Extract last available dates from context
    latest_equity_date = context['market.equity_eod']['MAX(trade_date)']
    latest_index_date = context['market.index_eod']['MAX(trade_date)']
    # Check today's date
    today = datetime.date.today()
    return {'freshness_status': latest_equity_date == today and latest_index_date == today}