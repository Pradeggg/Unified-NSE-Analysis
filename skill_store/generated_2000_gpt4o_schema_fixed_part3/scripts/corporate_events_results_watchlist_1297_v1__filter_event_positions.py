def run(context):
    events = context['event_list']
    threshold = context['score_threshold']
    return [event for event in events if event['score'] > threshold]