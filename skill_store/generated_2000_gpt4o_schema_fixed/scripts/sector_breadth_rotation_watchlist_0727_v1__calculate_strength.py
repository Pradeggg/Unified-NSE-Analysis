def run(context):
    # Example calculation logic
    return [{'sector': d['sector'], 'strength_score': d['pct_above_50dma']} for d in context['sector_data']]