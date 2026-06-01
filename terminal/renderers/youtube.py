"""Renderer for all YouTube-related intents."""

from terminal.renderers._base import _get, _source_trail_lines, FOOTER


def render(tool_results: list[dict]) -> str:
    """Render youtube_video_analysis, youtube_channel_latest, youtube_video_transcription,
    youtube_channel_transcription, and youtube_channels intents."""
    youtube = _get(tool_results, "analyze_youtube_video") or _get(tool_results, "analyze_youtube_channel_latest")
    youtube_channels = _get(tool_results, "list_youtube_channels")

    lines: list[str] = []

    if youtube and youtube.get("error"):
        lines.append("▶ YOUTUBE ANALYSIS")
        lines.append(f"  Error: {youtube.get('error')}")
        lines.append("")
    elif youtube:
        lines.append("▶ YOUTUBE MARKET INTELLIGENCE")
        selected = youtube.get("selected_channel") or {}
        latest = youtube.get("latest_video") or {}
        if selected:
            lines.append(f"  Selected channel: {selected.get('name') or selected.get('id')}")
        if latest:
            lines.append(f"  Latest video:     {latest.get('title') or latest.get('video_id')}")
        lines.append(f"  Title:   {youtube.get('title') or '—'}")
        lines.append(f"  Channel: {youtube.get('channel') or '—'}")
        lines.append(f"  Date:    {youtube.get('published_at') or '—'}")
        lines.append(f"  URL:     {youtube.get('url')}")
        transcript = youtube.get("transcript") or {}
        lines.append(
            f"  Transcript: {'available' if transcript.get('available') else 'unavailable'} "
            f"({transcript.get('segment_count', 0)} segments)"
        )
        if not transcript.get("available") and transcript.get("reason"):
            lines.append(f"  Transcript note: {transcript.get('reason')}")
        transcription = youtube.get("transcription") or {}
        if transcription.get("requested"):
            detail = (
                f"  Transcription: {transcription.get('status') or 'unknown'} "
                f"via {transcription.get('backend') or '—'}"
            )
            if transcription.get("model"):
                detail += f" ({transcription.get('model')})"
            lines.append(detail)
            if transcription.get("reason"):
                lines.append(f"  Transcription note: {transcription.get('reason')}")
            if transcription.get("temporary_audio_deleted"):
                lines.append("  Audio handling: temporary audio deleted after transcription")
        elif not transcript.get("available"):
            lines.append(
                "  To run speech-to-text explicitly: /youtube transcribe <channel|url> [--backend local|auto]"
            )
        lines.append(f"  Market relevance: {youtube.get('market_relevance')}")
        if youtube.get("artifact_path"):
            lines.append(f"  Artifact: {youtube.get('artifact_path')}")
        lines.append("")
        topics = youtube.get("market_topic_counts") or {}
        if topics:
            lines.append("▶ TOPIC SIGNALS")
            for topic, count in sorted(topics.items(), key=lambda kv: kv[1], reverse=True):
                lines.append(f"  {topic}: {count}")
            lines.append("")
        insights = youtube.get("market_insights") or []
        if insights:
            lines.append("▶ MARKET INSIGHTS")
            for insight in insights[:6]:
                lines.append(f"  • {insight}")
            lines.append("")
        segments = youtube.get("market_segments") or []
        lines.append("▶ TIMESTAMPED MARKET EXTRACTS")
        if segments:
            for segment in segments[:10]:
                lines.append(f"  {segment.get('timestamp', '—')}: {segment.get('excerpt', '')}")
        else:
            lines.append("  No market-specific transcript segments were detected.")
        lines.append("")
        followups = youtube.get("suggested_followups") or []
        if followups:
            lines.append("▶ FOLLOW-UP QUESTIONS")
            for idx, followup in enumerate(followups[:6], start=1):
                suffix = f" — {followup.get('why')}" if followup.get("why") else ""
                lines.append(f"  {idx}. {followup.get('prompt')}{suffix}")
            lines.append("")
        lines.append("▶ SOURCE POLICY")
        lines.append(f"  {youtube.get('source_policy')}")
        lines.append("")

    channels = (youtube_channels or {}).get("channels") or []
    lines.append("▶ PRESET YOUTUBE CHANNELS")
    if channels:
        for channel in channels:
            state = "enabled" if channel.get("enabled", True) else "disabled"
            feed = "latest-feed" if channel.get("has_latest_feed") else "manual-url"
            lines.append(
                f"  {channel.get('index', '—')}. {channel.get('name')} "
                f"[{state}; {feed}] — {channel.get('category', 'market')}"
            )
    else:
        lines.append("  No preset channels configured yet.")
    lines.append("")
    lines.append("▶ USAGE")
    lines.append("  /youtube")
    lines.append("  /youtube 1")
    lines.append("  /youtube <channel name>")
    lines.append("  /youtube <youtube-url>")
    lines.append("  /youtube transcribe 1 [--backend local|auto]")
    lines.append("  /youtube transcribe <youtube-url> [--backend local|auto]")
    lines.append("  /youtube channels")
    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)
