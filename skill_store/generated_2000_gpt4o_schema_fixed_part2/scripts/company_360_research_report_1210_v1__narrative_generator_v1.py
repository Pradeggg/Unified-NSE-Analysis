def run(context):
    # Process data to generate narrative
    narrative_text = generate_narrative(context)
    return {'narrative_text': narrative_text}