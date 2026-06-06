def run(data):
    latest_date = max(data, key=lambda x: x['period_end'])['period_end']
    return [entry for entry in data if entry['period_end'] == latest_date]