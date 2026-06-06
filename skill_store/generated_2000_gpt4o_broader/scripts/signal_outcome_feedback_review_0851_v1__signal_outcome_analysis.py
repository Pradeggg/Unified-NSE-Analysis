def run(context):
    summary = {}
    winners = []
    failures = []
    for signal in context['signal_log']:
        if signal['hit_target']:
            winners.append(signal)
        elif signal['hit_stop']:
            failures.append(signal)
    summary.update({'total_signals': len(context['signal_log']),
                    'total_winners': len(winners),
                    'total_failures': len(failures)})
    return {'outcome_summary': summary, 'winner_patterns': winners, 'failure_patterns': failures}