def run(context):
    import pandas as pd
    data = pd.DataFrame(context['signal_data'])
    # Example analysis
    winners = data[data['hit_target'] == 1]
    failures = data[data['hit_stop'] == 1]
    return {'winner_count': len(winners), 'failure_count': len(failures)}