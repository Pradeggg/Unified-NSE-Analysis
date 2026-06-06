def run(context):
    event_data = context['signals.corporate_events']
    if event_data.empty:
        return {'error': 'No event data available.'}
    upcoming_events = event_data[(event_data['event_date'] > '2023-07-01') & (event_data['event_date'] <= '2023-10-01')]
    result_reports = context['scores.results_analysis']
    recent_results = result_reports[(result_reports['created_at'] > '2023-07-01') & (result_reports['created_at'] <= '2023-10-01')]
    response = {
        'event_calendar': upcoming_events[['symbol', 'event_type', 'event_date', 'purpose_raw']],
        'symbol_watchlist': recent_results['symbol'].unique().tolist(),
        'result_context': [
            {
                'symbol': row['symbol'],
                'company_name': row['company_name'],
                'growth_yoy_revenue_pct': row['growth_yoy_revenue_pct'],
                'growth_qoq_revenue_pct': row['growth_qoq_revenue_pct']
            } for _, row in recent_results.iterrows()
        ],
        'action_bucket': 'Maintain watchlist based on recent performance.',
        'source_trail': upcoming_events[['source']].drop_duplicates().tolist()
    }
    return response