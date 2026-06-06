def run(context):
    data = context['data']
    for entry in data:
        entry['growth_yoy_revenue_pct'] = ... # Calculate YOY growth
        entry['growth_yoy_pat_pct'] = ... # Calculate YOY growth
    return data