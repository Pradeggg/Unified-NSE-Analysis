def run(context):
    symbol = context['symbol']
    data = query_from_database(symbol)
    return generate_analysis_report(data)