def run(context):
    # Process outcomes to create a summary of results
    successes = [s for s in context if s['hit_target']]
    failures = [s for s in context if s['hit_stop']]
    summary = {
        'total': len(context),
        'successes': len(successes),
        'failures': len(failures)
    }
    return {'outcome_summary': summary}