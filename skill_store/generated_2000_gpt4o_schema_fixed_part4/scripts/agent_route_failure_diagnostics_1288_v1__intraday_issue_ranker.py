def run(issue_counts):
    return sorted(issue_counts, key=lambda x: x['issue_count'], reverse=True)