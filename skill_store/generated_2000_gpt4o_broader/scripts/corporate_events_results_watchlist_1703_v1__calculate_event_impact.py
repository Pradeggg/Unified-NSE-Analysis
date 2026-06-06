def run(event_calendar, symbol_watchlist):
    # Example read-only analysis, likely more complex in reality
    impact_assessment = []
    for event in event_calendar:
        if event['symbol'] in symbol_watchlist:
            impact_assessment.append({
                'symbol': event['symbol'],
                'potential_impact': 'High' if event['event_type'] == 'Earnings' else 'Moderate'
            })
    return impact_assessment