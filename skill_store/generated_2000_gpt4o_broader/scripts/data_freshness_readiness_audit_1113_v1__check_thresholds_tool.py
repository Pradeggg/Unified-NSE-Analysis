def run(context):
    thresholds = context.get('thresholds', {})
    fresher_than = {}
    alerts = []
    for key, date in context.items():
        if date < thresholds.get(key, ''):  # assuming context has dates as strings
            alerts.append(f'{key} data is stale.')
        else:
            fresher_than[key] = date
    return {'freshness_status': fresher_than, 'alerts': alerts}