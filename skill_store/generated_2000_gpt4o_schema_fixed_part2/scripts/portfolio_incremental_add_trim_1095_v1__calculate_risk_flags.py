def run(context):
    # Simplified logic to illustrate concept
    risk_flags = []
    for record in context['records']:
        if record['stage'] != 'STAGE_2' or record['trading_signal'] not in ('BUY', 'STRONG_BUY'):
            risk_flags.append('HIGH_RISK')
        else:
            risk_flags.append('LOW_RISK')
    return risk_flags