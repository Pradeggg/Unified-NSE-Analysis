def run(context):
    # Analyze financial trends
    trends = extract_trends(context['financial_data'])
    return trends