def run(context):
    from datetime import datetime, timedelta
    today = datetime.now()
    return {table: (today - date).days for table, date in context['freshness_dates'].items()}