def run(context):
    fii_trend = context['fii_trend']
    dii_trend = context['dii_trend']
    regime = context['regime']
    ad_signal = context['ad_signal']
    trend_signal = context['trend_signal']
    
    risk_flags = {'risk_on': False}
    if fii_trend == 'Positive' and dii_trend == 'Positive' and regime == 'Bullish' and ad_signal == 'Bullish' and trend_signal == 'Bullish':
        risk_flags['risk_on'] = True
    return risk_flags