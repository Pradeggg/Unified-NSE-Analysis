def run(context):
    portfolio = context['portfolio']
    sector_changes = context.get('sector_changes', {})
    risk_report = {
        'high_risk': [],
        'low_risk': []
    }
    for holding in portfolio:
        symbol = holding.get('symbol')
        if symbol in sector_changes:
            monthly_change = sector_changes[symbol].get('change_1m_pct', 0)
            if monthly_change < -5:
                risk_report['high_risk'].append(symbol)
            else:
                risk_report['low_risk'].append(symbol)
    return risk_report