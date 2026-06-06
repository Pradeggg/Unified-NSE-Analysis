def run(context):
    # Sample analysis: calculate average relative strength per sector
    holdings = context['holdings_data']
    snapshots = context['snapshot_data']
    sector_insights = {}
    for snapshot in snapshots:
        sector = snapshot['sector']
        if sector not in sector_insights:
            sector_insights[sector] = {'total_strength': 0, 'count': 0}
        sector_insights[sector]['total_strength'] += snapshot['relative_strength']
        sector_insights[sector]['count'] += 1
    return {sector: insights['total_strength'] / insights['count'] for sector, insights in sector_insights.items()}