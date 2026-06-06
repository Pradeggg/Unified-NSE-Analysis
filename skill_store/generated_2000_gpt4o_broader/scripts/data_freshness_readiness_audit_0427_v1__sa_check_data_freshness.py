def run(context):
    from datetime import datetime, timedelta
    recent_dates = [datetime.now().date() - timedelta(days=i) for i in range(5)]
    fresh_data = [date for date in context['trade_date'] if date in recent_dates]
    freshness_report = {'fresh_count': len(fresh_data), 'expected_count': 5}
    return freshness_report