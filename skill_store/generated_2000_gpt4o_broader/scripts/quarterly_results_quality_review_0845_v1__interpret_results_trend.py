def run(context):
    data = context['data']
    # Analyze trends and return summary
    summary = {'risks': [], 'strengths': []}
    for result in data:
        if result['growth_qoq_revenue_pct'] < 0:
            summary['risks'].append(result['symbol'])
        else:
            summary['strengths'].append(result['symbol'])
    return {'summary': summary}