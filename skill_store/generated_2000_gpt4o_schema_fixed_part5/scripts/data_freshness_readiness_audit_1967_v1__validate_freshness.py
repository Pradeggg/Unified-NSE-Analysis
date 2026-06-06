def run(context):
    latest_equity = context['latest_equity_date']
    latest_stage = context['latest_stage_date']
    is_fresh = latest_equity == latest_stage
    return {'is_fresh': is_fresh}