def run(context):
    df = context['inputs'][0]
    insights = {'changes': [], 'anomalies': []}
    # Example analysis: trend in revenue
    if 'revenue' in df.columns:
        revenue_change = df['revenue'].pct_change().last_valid_index()
        insights['changes'].append({'field': 'revenue', 'change': revenue_change})
    return insights