def run(context):
    insights = []
    for record in context['inputs']:
        if record['verdict'] in ['miss', 'mixed']:
            insights.append(f"{record['symbol']} showed weak results with verdict: {record['verdict']}.")
    return {'insights': insights}