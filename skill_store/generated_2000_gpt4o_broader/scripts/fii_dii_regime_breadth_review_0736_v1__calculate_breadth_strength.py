def run(context):
    ad_oscillator = context['ad_oscillator']
    trin = context['trin']
    breadth_strength = ad_oscillator - trin
    return {'breadth_strength': breadth_strength}