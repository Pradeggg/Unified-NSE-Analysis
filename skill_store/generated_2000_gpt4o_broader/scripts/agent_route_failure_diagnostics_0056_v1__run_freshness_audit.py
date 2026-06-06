def run(context):
    from datetime import datetime
    
    run_ts = context.get('run_ts')
    analysis_date = context.get('analysis_date')
    
    quarter_start = datetime(datetime.now().year, (datetime.now().month-1)//3*3+1, 1)
    freshness_status = 'stale' if analysis_date < quarter_start else 'fresh'
    return {'freshness_status': freshness_status}