def run(context):
    advances = context.get('advances', 0)
    declines = context.get('declines', 0)
    ad_signal = context.get('ad_signal', '')
    trin_signal = context.get('trin_signal', '')
    breadth_context = ''
    if ad_signal == 'bullish' and trin_signal == 'bullish':
        breadth_context = 'Positive market breadth with strong buying interest.'
    elif ad_signal == 'bearish' or trin_signal == 'bearish':
        breadth_context = 'Negative market breadth indicating selling pressure.'
    else:
        breadth_context = 'Mixed signals in market breadth, indicating indecision.'
    return {'breadth_context': breadth_context}