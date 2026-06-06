def run(context):
    sector_exposure = {}
    for holding in context.get('portfolio.holdings', []):
        symbol = holding['symbol']
        stage_snapshot = next((s for s in context['scores.stage_snapshots'] if s['symbol'] == symbol), None)
        if stage_snapshot:
            sector = stage_snapshot.get('sector')
            price = stage_snapshot.get('price', 0)
            if sector:
                sector_exposure[sector] = sector_exposure.get(sector, 0) + holding['qty'] * price
    return sector_exposure