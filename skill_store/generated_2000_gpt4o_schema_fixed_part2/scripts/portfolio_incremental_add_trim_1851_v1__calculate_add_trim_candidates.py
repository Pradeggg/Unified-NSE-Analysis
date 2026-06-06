def run(holdings_data):
  add_candidates = []
  trim_candidates = []
  # Implement logic to suggest add or trim based on stage and trading signals.
  for holding in holdings_data:
    if holding['trading_signal'] in ['BUY', 'STRONG_BUY'] and holding['stage'] == 'STAGE_2':
      add_candidates.append(holding['symbol'])
    elif holding['trading_signal'] == 'SELL':
      trim_candidates.append(holding['symbol'])
  return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}