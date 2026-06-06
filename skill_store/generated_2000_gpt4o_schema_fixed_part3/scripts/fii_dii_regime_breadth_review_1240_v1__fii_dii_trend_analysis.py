def run(context):
    trend_strength = 'stable'
    if context['fii_net_5d'] > context['dii_net_5d']:
        trend_strength = 'fii dominance'
    elif context['dii_net_5d'] > context['fii_net_5d']:
        trend_strength = 'dii dominance'
    return {'flow_context': trend_strength}