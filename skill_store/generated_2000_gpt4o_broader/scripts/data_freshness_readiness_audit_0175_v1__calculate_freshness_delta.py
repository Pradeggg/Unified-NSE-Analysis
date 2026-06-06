def run(context):
    # Mock example of calculating delta between current date and last data entry date in context.
    freshness_matrix = {}
    for table, last_date in context.items():
        delta_days = (context['current_date'] - last_date).days
        freshness_matrix[table] = delta_days
    return freshness_matrix