def run(context):
    # Simulated validation logic
    validity_check = []
    for symbol in context['symbol_data']:
        if symbol['weekly_signal'] is None:
            validity_check.append({'symbol': symbol['symbol'], 'issue': 'missing weekly signal'})
    return {'validity_check': validity_check, 'report_summary': 'Validation complete.'}