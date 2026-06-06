# Analyze outcome summaries to identify winning and failing patterns.
def run(context):
    outcomes = context['outcome_summary']
    winner_patterns = []
    failure_patterns = []

    for outcome in outcomes:
        if outcome['hit_target']:
            winner_patterns.append(outcome['sector'])
        if outcome['hit_stop']:
            failure_patterns.append(outcome['sector'])

    return {'winner_patterns': set(winner_patterns), 'failure_patterns': set(failure_patterns)}