def run(context):
    # Analyze data to generate risk notes
    risk_notes = []
    for entry in context['insider_data']:
        if entry['avg_insider_score'] < 60:
            risk_notes.append(f"Potential risk: Low insider confidence for {entry['symbol']}")
    return risk_notes