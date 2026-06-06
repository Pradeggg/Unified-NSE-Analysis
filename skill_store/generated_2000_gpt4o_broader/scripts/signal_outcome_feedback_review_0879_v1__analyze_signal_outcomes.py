def run(context):
    hits = [row for row in context['signal_outcome_review'] if row['hit_target']]
    stops = [row for row in context['signal_outcome_review'] if row['hit_stop']]
    outcome_summary = {
        'total_signals': len(context['signal_outcome_review']),
        'successful_hits': len(hits),
        'failed_stops': len(stops)
    }
    # Identify patterns (dummy logic for illustration)
    winner_patterns = [hit['symbol'] for hit in hits if hit['return_pct'] > 5]
    failure_patterns = [stop['symbol'] for stop in stops if stop['return_pct'] < -5]
    return outcome_summary, winner_patterns, failure_patterns