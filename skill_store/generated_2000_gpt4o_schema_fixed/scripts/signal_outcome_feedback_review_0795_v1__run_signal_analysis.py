def run(context):
    summary = {}
    # Analyze winning signals
    winner_patterns = context[context['hit_target'] == True]
    if not winner_patterns.empty:
        summary['winner_patterns'] = winner_patterns['symbol'].value_counts().to_dict()
    # Analyze failure signals
    failure_patterns = context[context['hit_stop'] == True]
    if not failure_patterns.empty:
        summary['failure_patterns'] = failure_patterns['symbol'].value_counts().to_dict()
    return summary