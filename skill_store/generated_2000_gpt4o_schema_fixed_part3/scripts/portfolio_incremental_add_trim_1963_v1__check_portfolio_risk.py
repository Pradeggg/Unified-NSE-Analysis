def run(context):
    # Sample pseudo-code to evaluate risk levels
    portfolio_data = context['portfolio_data']
    risk_analysis = []
    for item in portfolio_data:
        risk_score = item['technical_score'] - item['stage_score']
        if risk_score < 0:
            risk_analysis.append({'symbol': item['symbol'], 'risk': 'high'})
        else:
            risk_analysis.append({'symbol': item['symbol'], 'risk': 'low'})
    return risk_analysis