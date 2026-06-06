
def run(context):
    fii_flow = context.inputs['fii_net_today']
    dii_flow = context.inputs['dii_net_today']
    regime = context.inputs['regime']
    ad_signal = context.inputs['ad_signal']
    trin_signal = context.inputs['trin_signal']

    flags = []

    if fii_flow > 0 and dii_flow > 0:
        flags.append('Positive Institutional Inflows')

    if regime == 'BULL' and ad_signal == 'BUY' and trin_signal == 'BULLISH':
        flags.append('Risk-On')
    elif regime == 'BEAR' or ad_signal == 'SELL' or trin_signal == 'BEARISH':
        flags.append('Risk-Off')
    else:
        flags.append('Neutral')

    context.outputs['risk_flags'] = flags

    return context.outputs