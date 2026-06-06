def run(context):
    # Extract insights from tracked signals
    winners = [signal for signal in context['tracked_signals'] if signal['hit_target']]
    losers = [signal for signal in context['tracked_signals'] if signal['hit_stop']]
    winner_patterns = [w['symbol'] for w in winners]
    failure_patterns = [l['symbol'] for l in losers]
    return winner_patterns, failure_patterns