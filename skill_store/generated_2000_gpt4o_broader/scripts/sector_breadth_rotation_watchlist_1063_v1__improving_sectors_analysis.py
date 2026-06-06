def run(context):
    sectors = context['sector_data']
    sorted_sectors = sorted(sectors, key=lambda x: x['avg_pct_above_50dma'], reverse=True)
    return sorted_sectors