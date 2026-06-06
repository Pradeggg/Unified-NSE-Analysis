def run(context):
    # Analyze context to summarize deals and context.
    results = []
    for item in context:
        summary = { 'symbol': item['symbol'], 'deal_info': item['deal'] }
        results.append(summary)
    return results