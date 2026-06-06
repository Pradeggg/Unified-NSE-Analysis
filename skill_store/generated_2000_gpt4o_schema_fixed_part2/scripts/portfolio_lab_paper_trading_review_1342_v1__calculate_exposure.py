def run(context):
    from collections import defaultdict
    exposure_summary = defaultdict(float)
    for signal in context['signals.signal_log']:
        exposure_summary[signal['symbol']] += float(signal['entry_low'])
    return exposure_summary