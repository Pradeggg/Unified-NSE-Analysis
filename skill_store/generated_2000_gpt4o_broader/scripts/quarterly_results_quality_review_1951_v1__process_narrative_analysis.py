# Python function (read-only)

def run(context):
    # Analyzing the narrative insights from the latest quarterly data
    insights = []
    for data in context['company_data']:
        insights.append({
            'symbol': data['symbol'],
            'company_name': data['company_name'],
            'narrative': data['pl_commentary'] or 'No commentary available'
        })
    return insights