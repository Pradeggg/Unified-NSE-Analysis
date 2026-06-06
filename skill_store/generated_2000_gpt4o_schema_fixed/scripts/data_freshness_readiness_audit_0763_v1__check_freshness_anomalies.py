def run(context):
    anomalies = {}  # Dictionary to store freshness anomalies
    # Compare latest trade dates against expected intervals
    for table, latest_date in context['latest_trade_dates'].items():
        if (context['current_date'] - latest_date).days > context['expected_refresh_intervals'][table]:
            anomalies[table] = 'Data freshness threshold exceeded'
    return {'anomaly_reports': anomalies}