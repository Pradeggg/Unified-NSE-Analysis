def run(context):
    trade_dates = context['trade_dates']
    current_date = datetime.datetime.now().date()
    freshness_report = {}
    for table, date in trade_dates.items():
        freshness_report[table] = (current_date - date).days <= 1
    return freshness_report