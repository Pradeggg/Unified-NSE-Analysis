def run(context):
    analysis = {}
    for symbol, avg_return, targets, stops in context['inputs']:
        analysis[symbol] = {
            'performance': 'winner' if avg_return > 0 else 'loser',
            'suggestions': 'Review strategy' if stops > targets else 'Continue'
        }
    return analysis