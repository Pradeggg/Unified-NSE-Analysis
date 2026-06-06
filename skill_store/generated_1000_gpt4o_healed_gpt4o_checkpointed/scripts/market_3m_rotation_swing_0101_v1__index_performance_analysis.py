def run(context):
    try:
        return {'index_returns': context['index_data']['change_pct_avg'], 'precision': 0.01}
    except KeyError:
        return {'index_returns': None, 'precision': 0.01}