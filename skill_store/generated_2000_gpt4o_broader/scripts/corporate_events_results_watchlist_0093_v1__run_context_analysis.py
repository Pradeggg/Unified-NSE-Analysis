def run(context):
    event_data = context['event_data']
    results_data = context['results_data']
    insights = []
    for event in event_data:
        matched_results = [result for result in results_data if result['symbol'] == event['symbol']]
        insights.append({'symbol': event['symbol'], 'event_detail': event['detail'], 'results': matched_results})
    return {'integrated_insights': insights}