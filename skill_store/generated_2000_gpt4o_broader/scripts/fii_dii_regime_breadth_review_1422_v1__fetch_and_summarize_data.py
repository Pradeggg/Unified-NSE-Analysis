def run(context):
    # Process and integrate data from inputs
    fiis, diis = sum([x['fii_net_5d'] for x in context['fii_dii_flows']]), sum([x['dii_net_5d'] for x in context['fii_dii_flows']])
    regime = max(context['market_regime'], key=lambda x: x['confidence'])
    breadth = context['breadth_data'][-1]['ad_signal']
    index_trend = context['index_data'][-1]['change_pct']
    return {
        'regime': regime['regime'],
        'flow_context': {'fii': fiis, 'dii': diis},
        'breadth_context': {'ad_signal': breadth},
        'index_confirmation': {'trend': index_trend},
        'risk_flags': detect_risks(fiis, diis, breadth, index_trend)
    }

def detect_risks(fii, dii, breadth, trend):
    risk_on = fii > 0 and breadth == 'positive' and trend > 0
    risk_off = dii < 0 or breadth == 'negative' or trend < 0
    return {'risk_on': risk_on, 'risk_off': risk_off}