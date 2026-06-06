def run(context):
    from datetime import datetime, timedelta
    latest_date = datetime.strptime(context['latest_date'], '%Y-%m-%d')
    today = datetime.now()
    delta = (today - latest_date).days
    freshness_status = 'fresh' if delta <= 1 else 'stale'
    return {'freshness_status': freshness_status}