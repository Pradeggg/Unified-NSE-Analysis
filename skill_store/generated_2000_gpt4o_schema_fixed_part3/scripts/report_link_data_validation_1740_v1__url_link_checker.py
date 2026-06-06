def run(context):
    results = {'valid_urls': [], 'invalid_urls': []}
    for url in context['url_list']:
        # Dummy check; replace with actual HTTP HEAD method
        if 'http://' in url or 'https://' in url:
            results['valid_urls'].append(url)
        else:
            results['invalid_urls'].append(url)
    return results