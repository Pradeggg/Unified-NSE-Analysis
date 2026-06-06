def run(context):
    return 'Positive' if context['opm_delta_pp'] > 0 else 'Negative'