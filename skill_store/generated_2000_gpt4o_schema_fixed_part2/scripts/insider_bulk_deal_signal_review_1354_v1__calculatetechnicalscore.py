def run(context):
    # Read only calculation for technical score
    symbol = context['symbol']
    snapshot_date = context['snapshot_date']
    # Mock calculation
    technical_score = 80  # Placeholder for real calculation
    return {'technical_score': technical_score}