def run(context):
    from datetime import datetime, timedelta
    max_lag = timedelta(days=context['max_allowed_lag_days'])
    freshness_issues = False
    current_date = datetime.now().date()
    for trade_date in context['trade_dates']:
        if current_date - trade_date > max_lag:
            freshness_issues = True
            break
    return {'freshness_issues': freshness_issues}