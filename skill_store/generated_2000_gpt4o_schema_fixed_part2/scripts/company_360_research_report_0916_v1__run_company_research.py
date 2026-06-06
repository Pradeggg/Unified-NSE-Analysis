def run(context):
    symbol = context['symbol']
    # Fetch data based on approved SQL templates
    latest_data = fetch_latest_data(symbol)
    # Synthesize data
    report = synthesize_report(latest_data)
    return report