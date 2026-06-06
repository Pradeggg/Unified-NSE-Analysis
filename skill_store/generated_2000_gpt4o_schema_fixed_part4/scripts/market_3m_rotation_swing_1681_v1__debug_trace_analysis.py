def run(context):
    # Generate debug trace from context data
    trace = {'index': context['index_returns'], 'stages': context['stage_distribution_change'], 'sectors': context['leading_sectors'], 'candidates': context['primary_candidates']}
    return trace