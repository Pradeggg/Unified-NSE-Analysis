def run(context):
    # Simulated validation logic
    validity_check = []
    for stock in context['stocks']:
        if stock['weekly_signal'] is None:
            validity_check.append({'symbol': stock['symbol'], 'issue': 'missing weekly signal'})
    return {'validity_check': validity_check, 'report_summary': 'Validation complete.'}