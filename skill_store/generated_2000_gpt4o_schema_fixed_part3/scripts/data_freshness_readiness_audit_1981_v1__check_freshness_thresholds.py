def run(context):
    latest_dates = context['inputs']['latest_dates']
    thresholds = context['inputs']['thresholds']
    freshness_matrix = {}
    missing_sources = []
    for table, latest_date in latest_dates.items():
        threshold = thresholds.get(table)
        if latest_date < threshold:
            missing_sources.append(table)
        freshness_matrix[table] = {'latest_date': latest_date, 'threshold': threshold}
    return {'freshness_matrix': freshness_matrix, 'missing_sources': missing_sources}