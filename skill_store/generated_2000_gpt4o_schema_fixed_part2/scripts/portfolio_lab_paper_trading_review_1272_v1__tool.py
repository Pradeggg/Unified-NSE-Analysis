def run(context):
    strategy_state = context.get('strategy_state', [])
    ranked_candidates = sorted(strategy_state, key=lambda x: x.get('investment_score', 0), reverse=True)
    return ranked_candidates