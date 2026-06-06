def run(context):
    from datetime import datetime
    run_ts = datetime.strptime(context['run_ts'], '%Y-%m-%d %H:%M:%S')
    analysis_date = datetime.strptime(context['analysis_date'], '%Y-%m-%d')
    delta = (run_ts - analysis_date).days
    return {'freshness_days': delta}