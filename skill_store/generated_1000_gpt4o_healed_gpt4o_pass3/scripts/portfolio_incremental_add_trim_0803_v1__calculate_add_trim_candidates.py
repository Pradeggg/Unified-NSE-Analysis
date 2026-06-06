
def run(context):
    add_candidates = []
    trim_candidates = []
    if 'fetch_current_holdings_results' in context:
        for holding in context['fetch_current_holdings_results']:
            matching_stage = next((s for s in context.get('evaluate_stages_results', []) if s['symbol'] == holding['symbol']), None)
            if matching_stage:
                if matching_stage['stage_score'] > 70 and matching_stage['trend_signal'] == 'UP':
                    add_candidates.append(holding['symbol'])
                elif matching_stage['stage_score'] < 30 or matching_stage['trend_signal'] == 'DOWN':
                    trim_candidates.append(holding['symbol'])
    return {
        'add_candidates': add_candidates,
        'trim_candidates': trim_candidates
    }
