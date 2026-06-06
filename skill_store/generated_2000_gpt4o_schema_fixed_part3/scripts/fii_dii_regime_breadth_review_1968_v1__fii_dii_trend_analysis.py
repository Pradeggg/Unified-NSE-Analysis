def run(context):
    fii_trend = context['fii'] > 0
    dii_trend = context['dii'] > 0
    return fii_trend or dii_trend