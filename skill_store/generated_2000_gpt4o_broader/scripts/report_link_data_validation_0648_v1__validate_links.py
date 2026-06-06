def run(context):
    broken_links = []
    for link in context['links']:
        # Simulate link validation
        if not link.startswith('http'):
            broken_links.append(link)
    return {'broken_links': broken_links}