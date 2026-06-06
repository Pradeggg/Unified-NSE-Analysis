def run(context):
    context['processed_market_data'] = {'status': 'processed'}
    return context['processed_market_data']