def run(context):
    freshness_issues = []
    for date_info in context['latest_dates']:
        if date_info['latest_date'] < context['quarter_start']:
            freshness_issues.append({'table': date_info['table'], 'issue': 'Data is not fresh'})
    return freshness_issues