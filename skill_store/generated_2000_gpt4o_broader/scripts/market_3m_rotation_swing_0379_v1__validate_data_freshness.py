def run(context):
    recent_date = context['market.index_eod'].max('trade_date')
    today = dt.date.today()
    return {'validation_report': today - recent_date <= dt.timedelta(days=1)}