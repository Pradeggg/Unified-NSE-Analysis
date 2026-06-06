def run(context):
    recent_runs = context['recent_runs']
    ranked_findings = sorted(recent_runs, key=lambda x: x['score'], reverse=True)
    return ranked_findings