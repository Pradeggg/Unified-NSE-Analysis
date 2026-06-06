def run(context):
    run_ids_with_issues = []
    for link in context.get('report_links', []):
        if not validate_link(link):
            run_ids_with_issues.append(link['run_id'])
    return {'suspected_broken_links': run_ids_with_issues}

# Function `validate_link` would be defined as a placeholder to demonstrate logic.