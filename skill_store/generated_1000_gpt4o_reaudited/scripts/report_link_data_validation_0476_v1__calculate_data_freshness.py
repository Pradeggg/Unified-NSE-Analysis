def run(context):
    from datetime import datetime, timedelta
    current_time = datetime.now()
    freshness_report = []
    for timestamp in context['run_timestamp_list']:
        run_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        freshness = current_time - run_time
        freshness_report.append({'run_id': timestamp, 'freshness_hours': freshness.total_seconds() / 3600})
    return freshness_report