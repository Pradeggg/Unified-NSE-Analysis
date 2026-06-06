def run(context):
    # Analyze trading signals and summarize performance
    signals_log = context['signals.signal_log']
    recent_strategies = signals_log[signals_log['date_issued'] >= pd.Timestamp.today() - pd.Timedelta(days=20)]
    summary = recent_strategies[['symbol', 'signal', 'entry_low', 'entry_high', 'stop_loss']].drop_duplicates()
    return summary.to_dict(orient='records')