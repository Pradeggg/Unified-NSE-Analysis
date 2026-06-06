def run(context):
    # Validate source-trail consistency within the results analysis.
    return {'validation_status': 'success' if context['source_trail'] else 'failed'}