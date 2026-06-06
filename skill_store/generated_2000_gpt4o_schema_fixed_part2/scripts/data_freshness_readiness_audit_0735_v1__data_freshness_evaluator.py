def run(context):
    freshness_matrix = {}
    blocking_gaps = []
    # Threshold comparison logic
    for table_name, latest_date in context['latest_dates'].items():
        if latest_date < context['thresholds'][table_name]:
            blocking_gaps.append(table_name)
        freshness_matrix[table_name] = latest_date
    return freshness_matrix, blocking_gaps