def run(context):
    # Calculate freshness gaps
    today = context['current_date']
    gaps = {}
    for table, latest_date in context['latest_trade_dates'].items():
        if today - latest_date > context['thresholds'][table]:
            gaps[table] = today - latest_date
    return {'freshness_analysis': gaps}