def run(context):
    results = analyze_signals(context['signals_data'])
    return results

def analyze_signals(data):
    # Analysis logic goes here
    return {
        'outcome_summary': 'Summary of results...',
        'winner_patterns': 'Patterns of successful signals...',
        'failure_patterns': 'Patterns of failing signals...'
    }