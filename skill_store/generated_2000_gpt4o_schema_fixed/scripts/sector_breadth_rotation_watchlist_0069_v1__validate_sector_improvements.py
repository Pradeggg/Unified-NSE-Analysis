def run(context):
    # Example validation logic
    validation_errors = []
    for rank in context['sector_ranks']:
        if rank['breadth_signal'] <= 0:
            validation_errors.append(f"Invalid breadth signal for sector {rank['sector']}")
    return validation_errors