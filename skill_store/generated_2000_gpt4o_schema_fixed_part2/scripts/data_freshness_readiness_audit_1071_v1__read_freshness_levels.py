def run(context):
    latest_dates = context['latest_dates']
    freshness_status = {}  # Assess freshness
    # Assume logic or complex checks return this:
    freshness_status['index_eod'] = 'Fresh'
    freshness_status['equity_eod'] = 'Fresh'
    return freshness_status