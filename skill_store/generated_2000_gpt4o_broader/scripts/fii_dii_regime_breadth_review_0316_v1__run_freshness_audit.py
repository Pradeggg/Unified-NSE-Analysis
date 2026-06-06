def run(context):
    timestamps = [context['timestamp_latest_fii'], context['timestamp_latest_regime'], context['timestamp_latest_breadth'], context['timestamp_latest_index']]
    if all(t == max(timestamps) for t in timestamps):
        return {'data_freshness': 'All data is up-to-date for the latest EOD'}
    else:
        return {'data_freshness': 'Data discrepancy found, not all EOD data is fresh'}