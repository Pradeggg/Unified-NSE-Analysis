def run(context):
    # Simple risk calculation based on index volatility
    index_volatility = max(context['index_returns']) - min(context['index_returns'])
    stage_dynamics = len(set(context['stage_distribution_change'])) / len(context['stage_distribution_change'])
    risks = {"volatility": index_volatility, "stage_variance": stage_dynamics}
    return risks