def run(context):
    risk_flags = []
    for row in context['combined_data']:
        risk_on = row['flow_signal'] == 'POSITIVE' and row['regime'] in ['BULL', 'RECOVERY'] and row['ad_signal'] == 'BULLISH'
        risk_off = row['flow_signal'] == 'NEGATIVE' or row['regime'] == 'BEAR' or row['ad_signal'] == 'BEARISH'
        risk_flags.append('RISK_ON' if risk_on else 'RISK_OFF' if risk_off else 'NEUTRAL')
    return risk_flags