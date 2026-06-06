def run(context):
    sector_ranks = context['sector_ranks']
    stage2_data = context['stage2_participation']
    # Map sectors from sector_ranks to stage2_participation
    results = []
    for rank in sector_ranks:
        for stage in stage2_data:
            if rank['sector'] == stage['sector']:
                momentum_score = rank['pct_above_50dma'] * stage['stage2_pct']
                results.append({'sector': rank['sector'], 'momentum_score': momentum_score})
    return {'momentum_indicators': sorted(results, key=lambda x: x['momentum_score'], reverse=True)}