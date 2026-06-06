def run(context):
    # Example read-only analysis function
    analysis = context['portfolio_analysis']
    add_candidates = [row['symbol'] for row in analysis if row['avg_stage_score'] > 70 and row['buy_signal']]
    trim_candidates = [row['symbol'] for row in analysis if row['avg_stage_score'] < 50]
    risk_flags = []  # Implement custom logic to determine risk flags
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates, 'risk_flags': risk_flags}