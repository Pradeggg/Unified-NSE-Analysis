def run(context):
    # Assess risks based on volatility and sector strength
    risk = 'High' if context['index_returns'] > 5 else 'Moderate'
    return {'risk_assessment': risk}