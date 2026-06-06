def run(context):
    run_ts = context['run_ts']
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    cutoff = now - timedelta(days=1)
    return {'is_fresh': run_ts >= cutoff}