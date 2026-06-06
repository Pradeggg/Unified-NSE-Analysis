
# Example Python diagnostic tool

def run(context):
    recent_runs = context['recent_run_data']
    symbol_issues = context['symbol_resolution_issues']
    gaps = context['tool_gaps']

    insights = []
    for run in recent_runs:
        if not run['stocks_filtered']:
            insights.append("Run ID {} has filtering issues.".format(run['run_id']))

    for issue in symbol_issues:
        insights.append("Symbol {} has a potential resolution issue.".format(issue['symbol']))

    for gap in gaps:
        insights.append("Potential tool gap for symbol {} in run {}.".format(gap['symbol'], gap['run_id']))

    recommendations = "Review tool configurations and update symbol mappings as required."

    return {'insights': insights, 'recommendations': recommendations}
