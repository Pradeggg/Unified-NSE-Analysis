def run(context):
    # Analyze market conditions
    if context['regime'] == 'BULL' and context['fii_net_today'] > 0:
        risk_level = 'Risk-On'
    elif context['regime'] == 'BEAR' or context['change_pct'] < 0:
        risk_level = 'Risk-Off'
    else:
        risk_level = 'Neutral'
    watchlist = {'focus': 'blue-chip'} if risk_level == 'Risk-On' else {'focus': 'defensive'}
    return {'risk_level': risk_level, 'watchlist': watchlist}