def run(context):
    threshold_date = context['threshold_date']
    freshness_issues = {}
    if context['index_date'] < threshold_date:
        freshness_issues['index_data'] = 'Stale'
    if context['equity_date'] < threshold_date:
        freshness_issues['equity_data'] = 'Stale'
    if context['snapshot_date'] < threshold_date:
        freshness_issues['snapshot_data'] = 'Stale'
    if context['breadth_date'] < threshold_date:
        freshness_issues['breadth_data'] = 'Stale'
    if context['ma_snapshot'] < threshold_date:
        freshness_issues['ma_data'] = 'Stale'
    if context['report_run'] < threshold_date:
        freshness_issues['report_run'] = 'Stale'
    return {'freshness_matrix': freshness_issues, 'blocking_gaps': any(freshness_issues.values())}