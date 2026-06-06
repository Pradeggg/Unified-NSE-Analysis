def run(context):
    outcomes = context['outcome_data']
    stages = context['stage_data']
    # Analyze and produce summary of winners and failures
    summary = {}
    patterns = {}
    return {'summary': summary, 'patterns': patterns}