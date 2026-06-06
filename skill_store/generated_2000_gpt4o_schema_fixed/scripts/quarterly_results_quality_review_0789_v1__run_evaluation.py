def run(context):
    # Analyze and summarize the latest quarterly results
    summary = {}
    for record in context:
        symbol = record['symbol']
        verdict = record['verdict']
        summary[symbol] = verdict
    return {'summary': summary}