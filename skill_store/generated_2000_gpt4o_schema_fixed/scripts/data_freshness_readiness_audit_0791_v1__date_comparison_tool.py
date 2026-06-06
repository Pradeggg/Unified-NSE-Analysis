def run(context):
    latest_dates = context['inputs']['latest_dates']
    expected_timeframes = context['inputs']['expected_timeframes']
    freshness_status = {}
    for table, date_info in latest_dates.items():
        freshness_status[table] = 'Fresh' if date_info >= expected_timeframes[table] else 'Stale'
    return {'freshness_status': freshness_status}