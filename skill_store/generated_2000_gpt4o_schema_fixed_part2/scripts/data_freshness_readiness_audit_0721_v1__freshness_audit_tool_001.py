def run(context):
    # Example code to compare dates
    latest_dates = context['inputs']
    if any(date is None for date in latest_dates.values()):
        return {'freshness_matrix': None, 'missing_sources': list(date for date, value in latest_dates.items() if value is None)}
    return {'freshness_matrix': latest_dates, 'missing_sources': []}