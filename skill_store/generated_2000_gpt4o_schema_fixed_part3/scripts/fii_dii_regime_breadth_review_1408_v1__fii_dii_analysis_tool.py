# Analyze FII/DII trends and market sentiment

def run(context):
    fii_trend = context['fii_trend']
    dii_trend = context['dii_trend']
    sentiment = context['market_sentiment']
    # Simple analysis logic
    if fii_trend == 'POSITIVE' and dii_trend == 'POSITIVE':
        flow_context = 'Strong institutional buying'
        risk_flags = 'Risk-on'
    elif fii_trend == 'NEGATIVE' or dii_trend == 'NEGATIVE':
        flow_context = 'Institutional selling pressure'
        risk_flags = 'Risk-off'
    else:
        flow_context = 'Mixed flows'
        risk_flags = 'Neutral'

    if sentiment == 'BEARISH':
        risk_flags = 'Risk-off'

    return {'flow_context': flow_context, 'risk_flags': risk_flags}