# Sample code to rank sectors by breadth measures
def run(context):
    sectors = context['sectors']
    breadth_measures = context['breadth_measures']
    ranked = sorted(sectors, key=lambda x: breadth_measures[x], reverse=True)
    return {'ranked_sectors': ranked}