def run(context):
    total_exposure = sum([entry['price_at_issue'] * 0.01 for entry in context['signal_logs']])
    return {'exposure_summary': total_exposure}