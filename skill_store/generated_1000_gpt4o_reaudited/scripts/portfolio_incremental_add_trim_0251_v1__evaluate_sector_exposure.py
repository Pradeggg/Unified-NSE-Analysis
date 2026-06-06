def run(context):
    sector_exposure = {}
    for holding in context['portfolio.holdings']:
        symbol = holding['symbol']
        sector = context['scores.stage_snapshots'].get(symbol, {}).get('sector')
        if sector:
            if sector not in sector_exposure:
                sector_exposure[sector] = 0
            sector_exposure[sector] += holding['qty'] * context['scores.stage_snapshots'].get(symbol, {}).get('price', 0)
    return sector_exposure