def run(context):
    # Analyze trend strength based on technical scores and price changes
    score = context['technical_score']
    change = context['price_change']
    trend_strength = 'Strong' if score > 70 and change > 2 else 'Weak'
    signals = 'Buy' if trend_strength == 'Strong' else 'Hold'
    return {'trend_strength': trend_strength, 'actionable_signals': signals}