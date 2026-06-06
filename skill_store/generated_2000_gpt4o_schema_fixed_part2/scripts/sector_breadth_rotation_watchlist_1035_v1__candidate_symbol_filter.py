def run(context):
    return [symbol for symbol in context['candidate_symbols'] if context['latest_stage'].get(symbol, {}).get('stage') == 'STAGE_2']