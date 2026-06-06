def run(run_data):
    from datetime import datetime as dt, timedelta
    freshness_issues = []
    one_week_ago = dt.now() - timedelta(days=7)
    for run in run_data:
        if dt.strptime(run['run_ts'], '%Y-%m-%d %H:%M:%S') < one_week_ago:
            freshness_issues.append(run['run_id'])
    return freshness_issues