def run(context):
    # Synthesize financial and market data context
    latest_data = fetch_latest_data(context['market_data'])
    financial_summary = summarize_financials(context['financials'])
    return {'synthesis': combine_insights(latest_data, financial_summary)}