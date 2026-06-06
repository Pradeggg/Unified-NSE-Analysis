def run(context):
    # Analyze trend data
    trends = context.inputs[0]
    if trends['fii_trend'] == 'up' and trends['dii_trend'] == 'up':
        return 'Strong institutional buying trend detected.'
    elif trends['fii_trend'] == 'down' and trends['dii_trend'] == 'down':
        return 'Strong institutional selling trend detected.'
    else:
        return 'Mixed trend; further analysis required.'