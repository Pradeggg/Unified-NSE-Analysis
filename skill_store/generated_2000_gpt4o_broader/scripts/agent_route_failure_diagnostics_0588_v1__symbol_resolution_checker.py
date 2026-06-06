def run(context):
    symbol = context.inputs['symbol']
    if context.get('stage_score', 0) < 0:
        return {'resolution_issue': 'Negative stage score detected', 'fix_suggestion': 'Reevaluate technical indicators.'}
    return {'resolution_issue': None, 'fix_suggestion': None}