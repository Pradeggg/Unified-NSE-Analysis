def run(context):
    latest_equity_date = context['latest_equity_date']
    latest_snapshot_date = context['latest_snapshot_date']
    freshness_summary = {}
    recommendation = ""
    if latest_equity_date < latest_snapshot_date:
        freshness_summary = {'status': 'stale', 'message': 'Equity data lags behind snapshots'}
        recommendation = 'Update equity EOD data.'
    else:
        freshness_summary = {'status': 'current', 'message': 'Data is current for analysis'}
    return freshness_summary, recommendation