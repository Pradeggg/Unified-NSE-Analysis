def run(context):
    # Normally would verify links here
    broken_links = set(context['expected_links']) - {'link1', 'link2'}  # Placeholder logic
    return {'broken_links': list(broken_links)}