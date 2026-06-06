def run(context):
    from datetime import datetime, timedelta
    run_ts = context['run_ts']
    now = datetime.utcnow()
    cutoff = now - timedelta(days=1)
    return {'is_fresh': run_ts >= cutoff}