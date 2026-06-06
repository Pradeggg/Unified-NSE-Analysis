def run(context):
    top_sectors = context['sector_data'].nlargest(5, 'avg_change_pct')
    return top_sectors['sector'].tolist()