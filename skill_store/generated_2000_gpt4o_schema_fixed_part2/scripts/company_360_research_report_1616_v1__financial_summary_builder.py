def run(context):
    # Stub code to synthesize financial summaries
    data = context['latest_data']
    return {'report_summary': f"Summary for {context['symbol']}: \n{data}"}