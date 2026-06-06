def run(context):
    return context['scores.stage_snapshots']['snapshot_date'].max()