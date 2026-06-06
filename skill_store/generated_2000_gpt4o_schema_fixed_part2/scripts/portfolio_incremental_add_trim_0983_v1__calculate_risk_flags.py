def run(context):
  risks = {}
  for symbol in context['symbols']:
    score = context['scores'].get(symbol)
    if score and score < 50:
      risks[symbol] = 'High Risk'
    else:
      risks[symbol] = 'Low Risk'
  return {'risk_flags': risks}