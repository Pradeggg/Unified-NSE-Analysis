def run(context):
    symbol_outcomes = {}
    for signal in context['signals.signal_log']:
        symbol = signal['symbol']
        if symbol not in symbol_outcomes:
            symbol_outcomes[symbol] = {'targets': 0, 'stops': 0}
        if signal['hit_target']:
            symbol_outcomes[symbol]['targets'] += 1
        if signal['hit_stop']:
            symbol_outcomes[symbol]['stops'] += 1
    return [{'symbol': symbol, 'outcome_summary': f"Targets: {outcomes['targets']}, Stops: {outcomes['stops']}"} for symbol, outcomes in symbol_outcomes.items()]
