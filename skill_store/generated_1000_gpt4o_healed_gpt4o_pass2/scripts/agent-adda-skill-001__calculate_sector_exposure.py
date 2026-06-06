def run(context):
    holdings = context['holdings'] if isinstance(context['holdings'], list) else []
    snapshots = context['snapshots'] if isinstance(context['snapshots'], list) else []
    sector_exposure = {}
    for holding in holdings:
        symbol = holding['symbol']
        qty = holding['qty']
        snapshot = next((s for s in snapshots if s['symbol'] == symbol), None)
        if snapshot:
            sector = snapshot['sector']
            sector_exposure[sector] = sector_exposure.get(sector, 0) + qty
    return {'sector_exposure': [{'sector': k, 'exposure': v} for k, v in sector_exposure.items()]}