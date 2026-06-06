def run(context):
    # Read and analyze trading signals
    trading_signals = context['trading_signal_data']
    # Identify candidates based on trading signals
    add_candidates = [x for x in trading_signals if x['trading_signal'] in ('BUY', 'STRONG_BUY')]
    trim_candidates = [x for x in trading_signals if x['trading_signal'] == 'SELL']
    return add_candidates, trim_candidates