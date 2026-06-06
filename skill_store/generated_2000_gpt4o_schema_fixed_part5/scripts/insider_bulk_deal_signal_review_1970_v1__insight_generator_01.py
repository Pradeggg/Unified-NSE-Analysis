def run(context):
    insider_data = context.inputs['insider_data']
    deal_data = context.inputs['deal_data']
    tech_data = context.inputs['technical_data']
    summary = {}
    for symbol in insider_data:
        if symbol in tech_data and tech_data[symbol]['trading_signal'] in ('BUY', 'STRONG_BUY'):
            summary[symbol] = {
                'insider_activity': insider_data[symbol],
                'bulk_deals': deal_data.get(symbol, []),
                'technical_score': tech_data[symbol]['technical_score']
            }
    context.outputs['summary_report'] = summary
    return context.outputs