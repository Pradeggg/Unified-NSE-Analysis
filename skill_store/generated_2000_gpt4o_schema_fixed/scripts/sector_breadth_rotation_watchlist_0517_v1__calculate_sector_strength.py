def run(context):
    sector_data = context['sector_data']
    stage_data = context['stage_data']
    # Calculate sector strength based on breadth and stage analysis
    strengths = {}
    for sector in sector_data:
        if sector in stage_data:
            strength = sector_data[sector]['pct_above_50dma'] + stage_data[sector]['relative_strength']
            strengths[sector] = strength
    return strengths