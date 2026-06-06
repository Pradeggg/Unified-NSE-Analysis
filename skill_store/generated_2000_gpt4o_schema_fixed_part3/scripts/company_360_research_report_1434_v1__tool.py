def run(context):
    evidence = context['evidence']
    # Perform read-only analysis with the provided evidence
    synthesis = synthesize_report(evidence)
    return synthesis