def run(context):
    latest_dates = context['inputs']['latest_dates']
    summary = f"Data is fresh as of {max(latest_dates)}."
    return {'freshness_summary': summary}