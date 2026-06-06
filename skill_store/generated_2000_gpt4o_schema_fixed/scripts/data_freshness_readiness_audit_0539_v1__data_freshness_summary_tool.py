def run(context):
    max_date = context['latest_trade_date']
    available_days = context['available_days']
    freshness_report = {
        'latest_trade_date': max_date,
        'sessions_covered': available_days
    }
    return freshness_report