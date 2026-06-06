def run(context):
    hit_targets = [s for s in context if s['hit_target']]
    hit_stops = [s for s in context if s['hit_stop']]
    successes = len(hit_targets)
    failures = len(hit_stops)
    patterns = {'successes': successes, 'failures': failures}
    return patterns