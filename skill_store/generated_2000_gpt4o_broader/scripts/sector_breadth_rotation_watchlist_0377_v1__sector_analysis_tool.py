def run(context):
    # Extract top sectors based on stage and breadth
    top_sectors = context.sector_data['sector'].unique()
    analysis = {}
    for sector in top_sectors:
        sector_stocks = context.price_data[context.price_data['sector'] == sector]
        analysis[sector] = sector_stocks.nlargest(5, 'change_1w_pct')
    return analysis