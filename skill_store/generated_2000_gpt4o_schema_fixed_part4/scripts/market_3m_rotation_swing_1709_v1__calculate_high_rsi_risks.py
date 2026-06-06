def run(context):
    # Sample analysis for risk assessment based on RSI
    indices = context['index_eod_data']
    risks = []
    for index in indices:
        if index['rsi'] < 30 and index['momentum_50d'] < 0:
            risks.append(index)
    return risks