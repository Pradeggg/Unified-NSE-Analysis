def run(context):
    latest_quarter = max(context['scores.quarterly_results']['period_end'])
    latest_snapshot = max(context['scores.stage_snapshots']['snapshot_date'])
    freshness_score = 0
    if latest_quarter > (latest_snapshot - pd.DateOffset(months=3)):
        freshness_score = 1
    return {'freshness_score': freshness_score}