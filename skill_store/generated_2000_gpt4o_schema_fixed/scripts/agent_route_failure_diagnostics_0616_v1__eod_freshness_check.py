def run(context):
    latest_run_ts = context['run_ts']
    latest_snapshot_date = context['snapshot_date']
    freshness_status = 'fresh' if latest_run_ts == latest_snapshot_date else 'stale'
    return {'freshness_status': freshness_status}