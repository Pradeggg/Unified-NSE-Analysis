def run(context):
    # Analyze the diagnostic logs and summarize the issues
    logs = context['diagnostic_logs']
    summary = analyze_logs(logs)
    return {'evaluation_summary': summary}