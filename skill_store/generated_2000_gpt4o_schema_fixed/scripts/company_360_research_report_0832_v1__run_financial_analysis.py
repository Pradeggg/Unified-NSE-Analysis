def run(context):
    financial_data = context['financial_data']
    summary = analyze_financials(financial_data)
    return {'analysis_summary': summary}