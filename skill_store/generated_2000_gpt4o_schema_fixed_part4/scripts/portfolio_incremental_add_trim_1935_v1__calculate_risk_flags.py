def run(context):
    risk_flags = []
    for symbol in context['symbols']:
        data = context['price_data'][symbol]
        if data['stage'] == 'STAGE_4' and data['trading_signal'] == 'SELL':
            risk_flags.append(symbol)
    return {'risk_flags': risk_flags}