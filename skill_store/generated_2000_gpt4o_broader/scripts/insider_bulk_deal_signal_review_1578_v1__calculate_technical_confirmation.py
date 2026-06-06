def run(context):
    confirmation = []
    for symbol, price, score in context:
        if score > 70:  # Assume 70 as a threshold for positive setup
            confirmation.append((symbol, True))
        else:
            confirmation.append((symbol, False))
    return confirmation