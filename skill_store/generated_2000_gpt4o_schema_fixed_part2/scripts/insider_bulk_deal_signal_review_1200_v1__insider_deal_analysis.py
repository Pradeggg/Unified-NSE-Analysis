def run(context):
    # Analyzes the provided context of alerts, deals, and technical scores.
    analysis_summary = []
    for alert in context['alerts']:
        relevant_deals = [deal for deal in context['deals'] if deal['symbol'] == alert['symbol']]
        tech_status = next((score for score in context['technical_scores'] if score['symbol'] == alert['symbol']), None)
        if relevant_deals and tech_status:
            analysis_summary.append({
                'symbol': alert['symbol'],
                'insider_entity': alert['entity'],
                'deal_qty': sum([deal['qty'] for deal in relevant_deals]),
                'tech_signal': tech_status['trading_signal']
            })
    return {'analysis_summary': analysis_summary}
