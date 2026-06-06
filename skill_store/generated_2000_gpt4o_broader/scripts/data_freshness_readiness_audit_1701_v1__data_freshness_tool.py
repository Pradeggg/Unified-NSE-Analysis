def run(context):
    freshness_matrix = {}
    # Populate freshness matrix with context data
    freshness_matrix['indices'] = context['last_update_indices']
    freshness_matrix['equity'] = context['last_update_equity']
    freshness_matrix['scores'] = context['last_snapshot_scores']
    freshness_matrix['breadth'] = context['last_breadth_update']
    freshness_matrix['moving_avg'] = context['last_ma_update']
    freshness_matrix['reports'] = context['last_run']
    return freshness_matrix