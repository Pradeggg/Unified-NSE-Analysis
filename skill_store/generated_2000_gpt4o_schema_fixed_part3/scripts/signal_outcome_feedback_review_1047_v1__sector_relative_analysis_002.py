def run(context):
    sector_data = context['sector_performance_data']
    summary = summarize_sector_performance(sector_data)
    return {'sector_performance_summary': summary}