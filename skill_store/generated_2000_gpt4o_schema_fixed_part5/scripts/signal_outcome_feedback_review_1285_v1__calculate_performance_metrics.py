def run(context):
    signals = context['signals_data']
    performance_summary = {
        'total_signals': len(signals),
        'targets_hit': sum(s['hit_target'] for s in signals),
        'stops_hit': sum(s['hit_stop'] for s in signals)
    }
    return performance_summary