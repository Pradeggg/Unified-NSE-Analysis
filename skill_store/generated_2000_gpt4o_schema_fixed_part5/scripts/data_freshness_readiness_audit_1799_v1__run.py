def run(context):
    # Extract the latest dates from the context as dictionaries
    latest_dates = context['latest_dates']
    freshness_matrix = {}

    # Check freshness for each required table
    for table, max_date in latest_dates.items():
        # Consider data fresh if the max_date is within the past week
        is_fresh = (context['current_date'] - max_date).days <= 7
        freshness_matrix[table] = is_fresh

    # Check for any missing data sources
    missing_sources = [
        table for table in context['required_tables']
        if table not in latest_dates
    ]

    return {'freshness_matrix': freshness_matrix, 'missing_sources': missing_sources}