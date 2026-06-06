def run(context):
    scores = context['inputs']
    signal_strength = []
    for score in scores:
        strength = score['vcp_score'] * score['enhanced_fund_score']
        signal_strength.append({'symbol': score['symbol'], 'signal_strength': strength})
    return {'outputs': signal_strength}