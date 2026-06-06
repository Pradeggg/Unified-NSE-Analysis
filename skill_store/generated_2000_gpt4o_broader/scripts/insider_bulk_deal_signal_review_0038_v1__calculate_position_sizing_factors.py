def run(context):
    # Calculate optimal position size based on inputs
    total_qty = context['total_qty']
    total_value = context['total_value']
    technical_score = context['technical_score']
    position_size = (total_qty * technical_score) / total_value
    return position_size