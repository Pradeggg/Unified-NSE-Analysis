def run(context):
    return {'snapshot_date': max(snapshot['snapshot_date'] for snapshot in context['scores.stage_snapshots'])}