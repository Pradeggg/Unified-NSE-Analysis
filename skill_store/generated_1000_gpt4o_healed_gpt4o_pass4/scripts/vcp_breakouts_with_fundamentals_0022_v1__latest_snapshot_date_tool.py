def run(context):
    snapshots = context.get('scores.stage_snapshots', [])
    if not snapshots:
        return {'snapshot_date': None}
    return {'snapshot_date': max(snapshot['snapshot_date'] for snapshot in snapshots)}