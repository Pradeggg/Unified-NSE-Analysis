# This tool verifies freshness across different datasets.
def run(context):
    index_date = context.get('latest_index_date')
    equity_date = context.get('latest_equity_date')
    stage_date = context.get('latest_stage_date')
    if index_date == equity_date == stage_date:
        return {'freshness_status': 'All datasets fresh and aligned.'}
    else:
        return {'freshness_status': 'Datasets not aligned; check individual freshness.'}