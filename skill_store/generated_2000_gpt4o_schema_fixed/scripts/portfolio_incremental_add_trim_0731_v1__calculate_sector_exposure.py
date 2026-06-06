def run(context):
    # Calculate sector exposure based on holdings and stage snapshots
    portfolio = context['portfolio_data']
    sector_exposure = {}
    for holding in portfolio:
        sector = holding['sector']
        qty = holding['qty']
        if sector not in sector_exposure:
            sector_exposure[sector] = 0
        sector_exposure[sector] += qty
    return sector_exposure