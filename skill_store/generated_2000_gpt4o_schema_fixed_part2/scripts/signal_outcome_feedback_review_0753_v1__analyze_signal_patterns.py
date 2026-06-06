def run(context):
    outcomes = context['outcome_summary']
    pattern_analysis = {'successful_patterns': [], 'failed_patterns': []}
    for outcome in outcomes:
        if outcome['hit_target']:
            pattern_analysis['successful_patterns'].append(outcome)
        elif outcome['hit_stop']:
            pattern_analysis['failed_patterns'].append(outcome)
    return pattern_analysis