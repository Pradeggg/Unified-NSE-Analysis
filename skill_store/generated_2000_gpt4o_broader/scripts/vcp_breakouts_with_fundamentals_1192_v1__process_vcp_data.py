def run(context):
    symbols = [entry['symbol'] for entry in context if entry['enhanced_fund_score'] > 7]
    return symbols