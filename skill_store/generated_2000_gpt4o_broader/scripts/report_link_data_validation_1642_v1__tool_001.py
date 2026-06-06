def run(context):
    validation_logging(context)
    inspect_links(context)
    return generate_debug_trace(context)