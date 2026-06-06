def run(context):
    eod_date = context['latest_eod_date']
    stage_date = context['latest_stage_snapshot']
    freshness_matrix = {
        'equity_eod_freshness': eod_date,
        'stage_snapshot_freshness': stage_date
    }
    return freshness_matrix