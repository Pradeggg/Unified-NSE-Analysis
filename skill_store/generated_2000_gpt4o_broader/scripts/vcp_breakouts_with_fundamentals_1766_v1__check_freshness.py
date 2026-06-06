def run(context):
    symbols = context['inputs']['symbol']
    latest_dates = context['inputs']['latest_dates']
    freshness_window = 10  # days
    from datetime import datetime, timedelta
    freshness_limit = datetime.now() - timedelta(days=freshness_window)
    is_fresh = [datetime.strptime(date, '%Y-%m-%d') > freshness_limit for date in latest_dates]
    return {
        'is_fresh': is_fresh
    }