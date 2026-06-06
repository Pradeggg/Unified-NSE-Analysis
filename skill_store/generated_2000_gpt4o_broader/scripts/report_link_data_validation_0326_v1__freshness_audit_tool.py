def run(context):
    recent_runs = context['recent_runs']
    freshness = []
    for run in recent_runs:
        # Check if run is older than expected freshness window
        if run['run_ts'] < (datetime.now() - timedelta(days=1)):
            freshness.append(run)
    return {'freshness_issues': freshness}