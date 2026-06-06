def run(context):
    # Sample implementation of a read-only outcome analysis
    signals = context['signals.signal_log']
    outcomes = {'outcome_summary': {}, 'winner_patterns': [], 'failure_patterns': []}
    for signal in signals:
        if signal['hit_target']:
            outcomes['winner_patterns'].append(signal)
        elif signal['hit_stop']:
            outcomes['failure_patterns'].append(signal)
    outcomes['outcome_summary'] = {
        'total_signals': len(signals),
        'success_rate': len(outcomes['winner_patterns']) / len(signals) if len(signals) > 0 else 0,
        'failure_rate': len(outcomes['failure_patterns']) / len(signals) if len(signals) > 0 else 0
    }
    return outcomes