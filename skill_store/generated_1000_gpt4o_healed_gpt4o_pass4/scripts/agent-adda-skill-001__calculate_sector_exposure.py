def run(context):
    holdings = context['holdings'] if isinstance(context['holdings'], list) else []
    snapshots = context['snapshots'] if isinstance(context['snapshots'], list) else []
    sector_exposure = []
    exposure_dict = {}
    for holding in holdings:
        symbol = holding['symbol']
        qty = holding['qty']
        snapshot = next((s for s in snapshots if s['symbol'] == symbol), None)
        if snapshot:
            sector = snapshot['sector']
            exposure_dict[sector] = exposure_dict.get(sector, 0) + qty
    sector_exposure = [{'sector': k, 'exposure': v} for k, v in exposure_dict.items()]
    return {'sector_exposure': sector_exposure} if sector_exposure else []