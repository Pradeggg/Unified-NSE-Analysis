def run(context):
    outcomes = {
        'total_signals': len(context['resolved_signals']),
        'hit_targets': len([s for s in context['resolved_signals'] if s['hit_target']]),
        'hit_stops': len([s for s in context['resolved_signals'] if s['hit_stop']]),
        'average_return': sum(s['return_pct'] for s in context['resolved_signals']) / len(context['resolved_signals']) if context['resolved_signals'] else 0
    }
    return outcomes