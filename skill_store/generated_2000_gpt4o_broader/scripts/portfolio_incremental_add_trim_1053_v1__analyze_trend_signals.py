def run(context):
  # Example code for analysis to be quarantined
  add_candidates = []
  trim_candidates = []
  risk_flags = []
  for row in context['data']:
    if row['trend_signal'] == 'positive' and row['stage_score'] > 50:
      add_candidates.append(row['symbol'])
    elif row['trend_signal'] == 'negative' or row['stage'] < 2:
      trim_candidates.append(row['symbol'])
    if row['change_1m_pct'] < -10:
      risk_flags.append(row['symbol'])
  return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates, 'risk_flags': risk_flags}