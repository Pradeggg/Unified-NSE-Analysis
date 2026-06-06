def run(context):
    portfolio, sector_changes = context
    risk_report = {
        'high_risk': [],
        'low_risk': []
    }
    for holding in portfolio:
        symbol = holding['symbol']
        if sector_changes[symbol]['change_1m_pct'] < -5:
            risk_report['high_risk'].append(symbol)
        else:
            risk_report['low_risk'].append(symbol)
    return [risk_report]