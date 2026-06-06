def run(context):
	add_trim_decisions = {}
	for symbol, stage_score, signal in context['symbols']:
		if signal in ['BUY', 'STRONG_BUY'] and stage_score > 50:
			add_trim_decisions[symbol] = 'ADD'
		elif signal == 'SELL' or stage_score < 30:
			add_trim_decisions[symbol] = 'TRIM'
		else:
			add_trim_decisions[symbol] = 'HOLD'
	return add_trim_decisions