def run(context):
    sector_data = context['sector_data']
    stage_data = context['stage_data']
    # Placeholder logic for demonstration
    ranked_sectors = sorted(sector_data, key=lambda x: x['change_5d'], reverse=True)
    return ranked_sectors