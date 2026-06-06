def run(context):
    ranked_candidates = context['ranked_candidates']
    # Calculation logic for position sizing
    position_sizes = {}
    total_weight = 100
    for candidate in ranked_candidates:
        position_sizes[candidate['symbol']] = total_weight / len(ranked_candidates)
    return {'position_sizes': position_sizes}