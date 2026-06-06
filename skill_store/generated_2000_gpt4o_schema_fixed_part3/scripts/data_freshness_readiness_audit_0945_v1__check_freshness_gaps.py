def run(context):
    from datetime import datetime, timedelta
    current_date = datetime.now()
    three_months_ago = current_date - timedelta(days=90)
    freshness_gaps = {}
    for table, latest_date in context['latest_dates'].items():
        if latest_date < three_months_ago:
            freshness_gaps[table] = f"Data is outdated: {latest_date.strftime('%Y-%m-%d')}"
    return freshness_gaps