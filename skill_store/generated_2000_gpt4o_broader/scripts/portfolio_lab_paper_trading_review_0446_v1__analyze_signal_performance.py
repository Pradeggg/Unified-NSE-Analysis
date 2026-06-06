def run(context):
    signal_data = context['signal_data']
    market_data = context['market_data']
    # Analyze signal performance
    performance_summary = {symbol: {'hit_targets': 0, 'missed_targets': 0} for symbol in set(signal_data['symbol'])}
    for signal in signal_data:
        symbol = signal['symbol']
        if signal['hit_target']:
            performance_summary[symbol]['hit_targets'] += 1
        else:
            performance_summary[symbol]['missed_targets'] += 1
    return performance_summary