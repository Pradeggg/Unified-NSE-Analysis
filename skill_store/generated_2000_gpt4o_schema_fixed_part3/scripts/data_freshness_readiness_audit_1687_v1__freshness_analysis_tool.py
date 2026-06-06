def run(context):
    latest_trade_date = context['latest_trade_date']
    expected_threshold = context['expected_threshold']
    # Analyze the freshness
    freshness_status = 'OK' if latest_trade_date >= expected_threshold else 'Delayed'
    delayed_sectors = []  # Perform sector-specific checks
    return {'freshness_status': freshness_status, 'delayed_sectors': delayed_sectors}