# Example pseudocode for context
# Filter and rank add candidates
add_candidates = filter(lambda x: x['trading_signal'] in ['BUY', 'STRONG_BUY'], context['joined_data'])
# Filter and rank trim candidates
trim_candidates = filter(lambda x: x['relative_strength'] < 0, context['joined_data'])
return {'ranked_add_candidates': sorted(add_candidates, key=lambda x: x['relative_strength'], reverse=True), 'ranked_trim_candidates': sorted(trim_candidates, key=lambda x: x['relative_strength'])}