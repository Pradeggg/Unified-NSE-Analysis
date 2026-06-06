def run(context):
    sector_data = context['sector_data']
    # Calculate relative strength based on available data
    # This is a dummy placeholder for actual logic
    relative_strength_scores = {sector: sum(data)/len(data) for sector, data in sector_data.items()}
    return {'relative_strength_scores': relative_strength_scores}