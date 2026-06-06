def run(context):
    valid_links = set(context.inputs['valid_links'])
    checked_links = set(context.inputs['checked_links'])
    broken_links = valid_links.difference(checked_links)
    remediation = f"Found {len(broken_links)} broken links."
    return {'broken_links': list(broken_links), 'remediation': remediation}