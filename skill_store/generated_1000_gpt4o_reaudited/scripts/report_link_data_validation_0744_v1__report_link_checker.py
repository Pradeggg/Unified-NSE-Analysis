def run(context):
    broken_links = []
    for link in context['report_links']:
        if not check_link_function(link):
            broken_links.append(link)
    return broken_links