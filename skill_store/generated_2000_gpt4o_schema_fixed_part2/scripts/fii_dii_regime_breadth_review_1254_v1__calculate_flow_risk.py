def run(context):
    fii_net = context['fii_net_today']
    dii_net = context['dii_net_today']
    regime = context['regime']
    risk_rating = 'Medium'
    if fii_net > 1000 and regime == 'BULL':
        risk_rating = 'Low'
    elif dii_net < -1000 and regime == 'BEAR':
        risk_rating = 'High'
    return {'risk_rating': risk_rating}