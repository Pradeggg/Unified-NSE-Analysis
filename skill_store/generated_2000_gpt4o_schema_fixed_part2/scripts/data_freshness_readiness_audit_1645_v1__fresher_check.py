def run(context):
    latest_index_date = context['index_eod_data']['latest_trade_date']
    latest_stage_date = context['stage_snapshot_data']['snapshot_date']
    is_fresh = latest_index_date == latest_stage_date
    return {'freshness_report': {'is_fresh': is_fresh}}