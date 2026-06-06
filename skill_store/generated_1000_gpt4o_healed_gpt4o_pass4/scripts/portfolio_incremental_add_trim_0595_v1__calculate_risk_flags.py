def run(context):
    risk_flags = []
    if 'stage_scores' in context:
        for score in context['stage_scores']:
            if score['stage_score'] < 2 and score['trend_signal'] == 'negative':
                risk_flags.append({'symbol': score['symbol'], 'risk': 'high'})
    return {'risk_flags': risk_flags}