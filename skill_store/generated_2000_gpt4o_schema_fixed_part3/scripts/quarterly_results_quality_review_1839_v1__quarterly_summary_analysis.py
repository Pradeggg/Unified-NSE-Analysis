def run(context):
    data = context.sql('SELECT symbol, verdict, opm_pct FROM scores.results_analysis WHERE verdict = 'beat' ORDER BY opm_pct DESC LIMIT 10')
    summary = [{'symbol': row['symbol'], 'opm': row['opm_pct']} for row in data]
    return summary