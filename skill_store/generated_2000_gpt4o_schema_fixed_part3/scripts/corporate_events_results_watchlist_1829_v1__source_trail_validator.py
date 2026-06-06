def run(context):
    for event in context['source_data']:
        if not event['source']:
            return False
    return True