def run(context):
    eod_dates = context['inputs']['eod_dates']
    snapshot_dates = context['inputs']['snapshot_dates']
    # Assess gaps
    freshness_matrix = {}
    for date in eod_dates:
        if date < 'current_date_minus_threshold':
            freshness_matrix['eod'] = 'stale'
    for date in snapshot_dates:
        if date < 'current_date_minus_threshold':
            freshness_matrix['snapshot'] = 'stale'
    missing_sources = []
    return {'freshness_matrix': freshness_matrix, 'missing_sources': missing_sources}