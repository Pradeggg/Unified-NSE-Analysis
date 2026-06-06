def run(context):
    broken_links = []
    if 'report_links' in context:
        for link in context['report_links']:
            if not check_link_function(link):
                broken_links.append(link)
    return {'broken_links_identified': broken_links}