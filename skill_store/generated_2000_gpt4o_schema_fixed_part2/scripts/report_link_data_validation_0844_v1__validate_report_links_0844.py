def run(context):
    results = []
    # Simulated code to validate report links
    for link in context['report_links']:
        if 'invalid' in link:
            results.append({'link': link, 'valid': False})
        else:
            results.append({'link': link, 'valid': True})
    return {'validated_links': results}