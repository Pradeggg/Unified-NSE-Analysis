def run(context):
    holdings = context['holdings_data']
    sector_exposure = {}
    for holding in holdings:
        sector = holding['sector']
        sector_exposure[sector] = sector_exposure.get(sector, 0) + holding['investment_score']
    return {'sector_exposure_analysis': sector_exposure}