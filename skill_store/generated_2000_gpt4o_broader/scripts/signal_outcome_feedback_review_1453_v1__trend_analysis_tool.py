def run(context):
    import pandas as pd
    signal_data = context['signal_data']
    # Perform read-only trend analysis on signal data
    trend_patterns = signal_data.groupby('sector').apply(lambda x: x[x['hit_target'] == True].shape[0] / x.shape[0])
    trend_patterns = trend_patterns.reset_index(name='success_rate')
    return {'trend_patterns': trend_patterns}