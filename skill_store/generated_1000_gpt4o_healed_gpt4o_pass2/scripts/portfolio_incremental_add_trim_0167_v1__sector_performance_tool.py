def run(context):
    sector_performance = context['sector_exposure']
    sector_ranking = sorted(sector_performance, key=lambda x: x['exposure'], reverse=True)
    return sector_ranking