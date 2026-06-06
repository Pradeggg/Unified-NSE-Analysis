def run(context):
    # Analyze risk based on index returns and primary candidates
    risks = []
    for candidate in context['primary_candidates']:
        # Demo risk metric: RSI overbought situation
        if candidate['rsi'] > 70:
            risks.append({'symbol': candidate['symbol'], 'risk': 'High RSI'})
    return risks