def run(context):
    results = {}
    current_date = datetime.date.today()
    # Compare latest dates with current_date and thresholds
    for key, date in context.items():
        if (current_date - date).days > 1:  # Example threshold
            results[key] = 'Stale'
        else:
            results[key] = 'Fresh'
    return results