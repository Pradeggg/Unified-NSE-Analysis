def run(context):
    sector_strengths = context['sector_data']
    sorted_sectors = sorted(sector_strengths, key=lambda x: x['stage_score'], reverse=True)
    return sorted_sectors[:5]