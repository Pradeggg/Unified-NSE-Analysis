def run(context):
    from datetime import datetime, timedelta
    recent_runs = [run for run in context['validated_runs'] if run['run_ts'] > datetime.now() - timedelta(days=7)]
    return {'freshness_analysis': recent_runs}