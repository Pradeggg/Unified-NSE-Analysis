def run(context):
    # Calculate sector breadth and rank sectors based on various metrics
    breadth = context['sector_data'].groupby('sector').agg({'breadth_signal':'count'})
    top_sectors = breadth.sort_values(by='breadth_signal', ascending=False).head(10)
    return top_sectors.to_dict()