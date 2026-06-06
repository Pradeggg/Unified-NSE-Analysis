def run(context):
    holdings = context.get('portfolio.holdings', [])
    if not holdings:
        return {'error': 'No holdings data available'}
    sector_changes = context.get('scores.stage_snapshots', [])
    risk_report = {
        'high_risk': [],
        'low_risk': []
    }
    for holding in holdings:
        symbol = holding.get('symbol')
        relevant_changes = next((item for item in sector_changes if item['symbol'] == symbol), None)
        if relevant_changes and relevant_changes.get('change_1m_pct', 0) < -5:
            risk_report['high_risk'].append(symbol)
        else:
            risk_report['low_risk'].append(symbol)
    return risk_report