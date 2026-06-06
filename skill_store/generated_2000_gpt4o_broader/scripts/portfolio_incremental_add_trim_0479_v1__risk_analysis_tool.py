def run(context):
    risk_flags = []
    for record in context['data']:
        if record['stage'] == '4' and record['qty'] > 0:
            risk_flags.append({'symbol': record['symbol'], 'risk': 'consider trimming due to Stage 4'})
    return risk_flags