def run(context):
    broken_links = []
    for link in context.get('links', []):
        if not link_is_valid(link):
            broken_links.append(link)
    return {'broken_links': broken_links}