def run(context):
    threshold_date = date.today() - timedelta(days=7)
    freshness_results = {}
    for key, last_date in context['last_dates'].items():
        is_fresh = last_date >= threshold_date
        freshness_results[key] = {
            'is_fresh': is_fresh,
            'comments': '' if is_fresh else f'{key} data is stale.'
        }
    return freshness_results