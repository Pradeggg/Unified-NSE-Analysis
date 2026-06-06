def run(context):
    # Read-only analysis on data freshness
    # Only for illustrative purposes
    return {'freshness_status': 'OK' if context['trade_date'] == latest_known_date else 'STALE'}