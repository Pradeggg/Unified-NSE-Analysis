def run(context):
    results = {}
    thresholds = context['alert_thresholds']
    for table, details in context['approved_tables'].items():
        if details['last_trade_date'] < thresholds['acceptable_date']:
            results[table] = 'Stale'
        else:
            results[table] = 'Fresh'
    return results