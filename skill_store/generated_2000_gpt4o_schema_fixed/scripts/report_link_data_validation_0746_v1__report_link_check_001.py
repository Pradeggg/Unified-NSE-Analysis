def run(context):
    return [link for link in context.run_id if not validate_link(link)]

def validate_link(link):
    # Simulated link validation (read-only)
    return True