def run(context):
    signals = context['signal_data']
    # Analyze winner and loser patterns
    winners = [s for s in signals if s['hit_target']]
    losers = [s for s in signals if s['hit_stop']]
    summary_report = {
        'outcome_summary': 'Evaluated signal outcomes for the past 3 months.',
        'winner_patterns': len(winners),
        'failure_patterns': len(losers),
        'route_improvements': 'Identify strategies where signals consistently hit targets.',
        'next_checks': 'Review fundamental and technical scores for improvement.'
    }
    return summary_report