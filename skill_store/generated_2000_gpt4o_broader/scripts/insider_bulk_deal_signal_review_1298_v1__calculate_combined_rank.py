def run(context):
    deals = context['deal_summary']
    tech = context['technical_confirmation']
    ranked = sorted(deals, key=lambda x: tech[x['symbol']]['technical_score'], reverse=True)
    return [d['symbol'] for d in ranked]