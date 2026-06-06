def run(context):
    hits = [s for s in context if s['hit_target']]
    stops = [s for s in context if s['hit_stop']]
    return {'pattern_analysis': {'targets_hit': len(hits), 'stops_hit': len(stops)}}