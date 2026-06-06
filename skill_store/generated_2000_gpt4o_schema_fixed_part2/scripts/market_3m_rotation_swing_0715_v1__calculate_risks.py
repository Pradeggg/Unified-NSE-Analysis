def run(context):
    index_returns = context['index_returns']
    stage_dist = context['stage_distribution_change']
    risks = []
    for index, returns in index_returns.items():
        if returns < -5:
            risks.append(f'High risk in {index} with returns at {returns}%')
    return risks