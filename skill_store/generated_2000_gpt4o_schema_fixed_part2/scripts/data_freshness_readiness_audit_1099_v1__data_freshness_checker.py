def run(context):
    data = context['latest_index_eod'], context['latest_equity_eod'], context['latest_stage_snapshots']
    # perform freshness readiness checks
    return {'freshness_matrix': data}