def run(context):
    financials = context['latest_financials']
    # Analyze financial trends
    summary = analyze_trends(financials)
    return summary