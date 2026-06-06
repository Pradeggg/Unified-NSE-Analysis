def run(context):
  last_price = context['last_price']
  week52_high = context['week52_high']
  freshness_audit_score = (last_price / week52_high) * 100
  return {'freshness_audit_score': freshness_audit_score}