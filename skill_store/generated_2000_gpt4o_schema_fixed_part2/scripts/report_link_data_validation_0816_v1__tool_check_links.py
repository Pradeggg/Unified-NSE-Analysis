def run(context):
    # Hypothetical logic for checking report link validity
    # Read-only and does not perform actions beyond analysis
    broken = []
    for link in context['report_links']:
        # Placeholder for link validation logic
        if not link.endswith('.pdf'):
            broken.append(link)
    return {'broken_links': broken}