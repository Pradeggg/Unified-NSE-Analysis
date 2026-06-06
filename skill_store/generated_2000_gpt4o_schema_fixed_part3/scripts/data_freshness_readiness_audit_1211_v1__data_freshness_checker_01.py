def run(context):
    index_date = context['latest_index_eod']
    equity_date = context['latest_equity_eod']
    stage_date = context['latest_stage_snapshot']
    freshness_matrix = {
        'Index EOD Freshness': index_date,
        'Equity EOD Freshness': equity_date,
        'Stage Snapshot Freshness': stage_date
    }
    return freshness_matrix