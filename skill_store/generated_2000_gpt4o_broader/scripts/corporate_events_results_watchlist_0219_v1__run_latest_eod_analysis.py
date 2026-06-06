def run(context):
    # Pseudocode for combining event and results analysis
    events = context['signals.corporate_events']
    results = context['scores.results_analysis']
    merged_data = []
    for event in events:
        if event['symbol'] in results:
            result = results[event['symbol']]
            merged_data.append({
                'symbol': event['symbol'],
                'event_date': event['event_date'],
                'event_type': event['event_type'],
                'impact_score': result['score']
            })
    return merged_data