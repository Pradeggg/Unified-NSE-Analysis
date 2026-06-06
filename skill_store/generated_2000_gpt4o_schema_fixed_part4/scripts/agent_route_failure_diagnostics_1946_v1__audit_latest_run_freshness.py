def run(context):
    # Check if the latest run is within the last 3 months
    is_fresh = context['run_ts'] >= (CURRENT_DATE - INTERVAL '3 months')
    return 'Fresh' if is_fresh else 'Stale'