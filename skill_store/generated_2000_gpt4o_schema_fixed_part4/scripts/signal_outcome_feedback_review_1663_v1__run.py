def run(context):
    results = context['sql_result']
    # Analyze results to extract actionable insights
    # [ ...code to process results... ]
    return {
        'outcome_summary': "Summary of signal outcomes",
        'winner_patterns': "Identified patterns from successful signals",
        'failure_patterns': "Analysis of failed signals",
        'route_improvements': "Proposed strategy adjustments",
        'next_checks': "Suggested follow-up actions"
    }