def run(context):
    outcomes = context['outcome_summary']
    winners = [o for o in outcomes if o['hit_target']]
    failures = [o for o in outcomes if o['hit_stop']]
    return {
        'winner_patterns': analyze_winners(winners),
        'failure_patterns': analyze_failures(failures)
    }

# Helper functions to analyze winners and failures
# (Definitions for `analyze_winners`, `analyze_failures` not shown)