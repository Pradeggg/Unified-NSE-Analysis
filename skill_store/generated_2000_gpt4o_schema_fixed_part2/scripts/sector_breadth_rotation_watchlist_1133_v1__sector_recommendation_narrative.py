def run(context):
    sectors = context['sector_ranks']
    improving = context['improving_sectors']
    narrative = 'Sectors showing improvement include: ' + ', '.join(sectors) + '. Leading sectors in Stage 2 are: ' + ', '.join(improving) + '.'
    return {'narrative_summary': narrative}