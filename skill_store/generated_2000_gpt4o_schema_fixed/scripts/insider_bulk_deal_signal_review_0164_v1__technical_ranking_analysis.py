def run(context):
	# Sample Python tool to rank symbols based on scores and signals
	data = context['scores.stage_snapshots']
	ranked = data.sort_values(by=['stage_score', 'trading_signal'], ascending=[False, True])
	return ranked['symbol'].tolist()[:10]