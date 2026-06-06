# Example tool code
def run(context):
    sector_data = context['inputs']['sector_data']
    analysis = analyze_sectors(sector_data)
    return {'sector_analysis': analysis}