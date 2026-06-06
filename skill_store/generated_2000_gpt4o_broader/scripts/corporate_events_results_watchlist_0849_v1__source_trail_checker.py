def run(context):
    # Example: Verify source-trail presence for each event.
    verified = []
    for event in context['event_data']:
        if 'source' in event:
            verified.append(event)
    for result in context['results_data']:
        if 'source_trail' in result:
            verified.append(result)
    return verified