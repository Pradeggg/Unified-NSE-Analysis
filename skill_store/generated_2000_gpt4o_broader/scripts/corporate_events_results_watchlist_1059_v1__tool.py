def run(context):
    event_data = context['event_data']
    results_data = context['results_data']
    validated_data = []
    for event in event_data:
        for result in results_data:
            if event['symbol'] == result['symbol']:
                validated_data.append({
                    'symbol': event['symbol'],
                    'event_type': event['event_type'],
                    'growth_yoy_revenue': result['growth_yoy_revenue_pct'],
                    'growth_qoq_revenue': result['growth_qoq_revenue_pct']
                })
    return validated_data