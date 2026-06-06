def run(context):
    result = {'is_valid': [], 'broken_links': []}
    for run_id in context['run_id']:
        link_validation = fake_link_validation(run_id)  # Placeholder
        result['is_valid'].append(link_validation['is_valid'])
        if not link_validation['is_valid']:
            result['broken_links'].append(link_validation['broken'])
    return result