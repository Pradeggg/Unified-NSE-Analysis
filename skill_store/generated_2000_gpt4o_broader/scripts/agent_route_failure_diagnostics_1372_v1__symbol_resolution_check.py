# Sample function to analyze symbol resolution
    def run(context):
        resolution_status = []
        likely_causes = []
        for entry in context['inputs']:
            if entry['trend_signal'] == 'off':
                resolution_status.append('unresolved')
                likely_causes.append('Missing symbol data in snapshot')
            else:
                resolution_status.append('resolved')
        return resolution_status, likely_causes