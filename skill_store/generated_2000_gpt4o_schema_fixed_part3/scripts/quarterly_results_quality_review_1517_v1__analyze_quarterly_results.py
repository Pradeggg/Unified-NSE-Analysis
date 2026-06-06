def run(context):
    latest_results = context['latest_quarterly_results']
    # Analyze top performers based on revenue and PAT growth
    top_performers = sorted(latest_results, key=lambda x: (x['revenue'], x['pat']), reverse=True)[:5]
    return top_performers