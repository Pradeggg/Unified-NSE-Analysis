def run(context):
    outcome_summary = {}
    winner_patterns = []
    failure_patterns = []
    results = context['last_3_months_signal_outcomes']
    # Analyze results for patterns
    for result in results:
        if result['hit_target']:
            winner_patterns.append(result)
        elif result['hit_stop']:
            failure_patterns.append(result)
    outcome_summary['total_signals'] = len(results)
    outcome_summary['successful_signals'] = len(winner_patterns)
    outcome_summary['failed_signals'] = len(failure_patterns)
    return outcome_summary, winner_patterns, failure_patterns