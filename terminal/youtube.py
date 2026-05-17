"""YouTube market-intelligence ingestion helpers."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

import requests

ROOT = Path(__file__).resolve().parent.parent
CHANNEL_REGISTRY = ROOT / "data" / "youtube_channels.json"
ARTIFACT_DIR = ROOT / "data" / "youtube_market"
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
CHANNEL_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
DEFAULT_TRANSCRIBE_BACKEND = os.environ.get("AGENT_ADDA_YOUTUBE_TRANSCRIBE_BACKEND", "local").strip().lower() or "local"
DEFAULT_WHISPER_MODEL = os.environ.get("AGENT_ADDA_YOUTUBE_WHISPER_MODEL", "base").strip() or "base"

MARKET_TERMS = {
    "nifty", "bank nifty", "sensex", "midcap", "smallcap", "smid", "sector", "sectors",
    "stock", "stocks", "market", "markets", "breakout", "support", "resistance",
    "fii", "dii", "earnings", "results", "valuation", "inflation", "rate", "rates",
    "rupee", "usd", "crude", "gold", "rbi", "fed", "profit", "revenue", "margin",
    "guidance", "capex", "demand", "order book", "banking", "pharma", "healthcare",
    "it sector", "metal", "energy", "auto", "fmcg", "realty", "defence", "nasdaq", "ai",
}


@dataclass(frozen=True)
class YouTubeVideoRef:
    video_id: str
    canonical_url: str
    start_seconds: int | None = None


def load_youtube_channel_registry(path: Path = CHANNEL_REGISTRY) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "channels": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("channels"), list):
        data["channels"] = []
    return data


def list_youtube_channels() -> dict[str, Any]:
    channels = [c for c in load_youtube_channel_registry().get("channels", []) if c.get("enabled", True)]
    return {
        "status": "ok",
        "count": len(channels),
        "enabled_count": len(channels),
        "channels": [
            {**channel, "index": idx, "has_latest_feed": bool(channel.get("channel_id"))}
            for idx, channel in enumerate(channels, start=1)
        ],
        "registry_path": str(CHANNEL_REGISTRY.relative_to(ROOT)),
    }


def _select_channel(selection: str | int) -> tuple[dict[str, Any] | None, str | None]:
    channels = list_youtube_channels().get("channels", [])
    raw = str(selection or "").strip()
    if not channels:
        return None, "No enabled YouTube channels configured"
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(channels):
            return channels[idx - 1], None
        return None, f"Channel number {idx} is out of range"
    needle = raw.lower()
    for channel in channels:
        haystack = " ".join(str(channel.get(k) or "") for k in ("id", "name", "channel_url", "category")).lower()
        if needle and needle in haystack:
            return channel, None
    return None, f"No preset YouTube channel matched '{raw}'"


def parse_youtube_url(source: str) -> YouTubeVideoRef:
    parsed = urlparse((source or "").strip())
    host = parsed.netloc.lower()
    if host not in YOUTUBE_HOSTS:
        raise ValueError("Not a supported YouTube URL")
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith(("/shorts/", "/embed/")):
        video_id = parsed.path.strip("/").split("/")[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id or ""):
        raise ValueError("Could not resolve a YouTube video id")
    return YouTubeVideoRef(video_id, WATCH_URL.format(video_id=video_id), _parse_start_seconds(parsed))


def _parse_start_seconds(parsed) -> int | None:
    values = parse_qs(parsed.query).get("t") or parse_qs(parsed.query).get("start") or []
    if not values:
        return None
    raw = values[0].strip().lower()
    if raw.isdigit():
        return int(raw)
    total = 0
    matched = False
    for value, unit in re.findall(r"(\d+)([hms])", raw):
        matched = True
        n = int(value)
        total += n * 3600 if unit == "h" else n * 60 if unit == "m" else n
    return total if matched else None


def _http_get(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def _extract_json_object(page: str, var_name: str) -> dict[str, Any]:
    idx = page.find(f"{var_name} = ")
    if idx < 0:
        idx = page.find(f"{var_name}=")
    if idx < 0:
        return {}
    start = page.find("{", idx)
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(page)):
        ch = page[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(page[start:pos + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _video_details(player_response: dict[str, Any]) -> dict[str, Any]:
    details = player_response.get("videoDetails") or {}
    micro = player_response.get("microformat", {}).get("playerMicroformatRenderer", {})
    return {
        "video_id": details.get("videoId"),
        "title": details.get("title") or micro.get("title", {}).get("simpleText"),
        "channel": details.get("author") or micro.get("ownerChannelName"),
        "channel_id": details.get("channelId") or micro.get("externalChannelId"),
        "published_at": micro.get("publishDate") or micro.get("uploadDate"),
        "duration_seconds": int(details.get("lengthSeconds") or 0) if str(details.get("lengthSeconds") or "").isdigit() else None,
        "short_description": details.get("shortDescription") or "",
    }


def _fetch_transcript_from_player_response(player_response: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tracks = player_response.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks") or []
    tracks = [track for track in tracks if track.get("baseUrl")]
    if not tracks:
        return [], {"available": False, "reason": "No caption tracks exposed on the watch page"}
    selected = next((t for t in tracks if str(t.get("languageCode", "")).lower().startswith("en")), tracks[0])
    xml_text = _http_get(selected["baseUrl"])
    root = ElementTree.fromstring(xml_text)
    segments: list[dict[str, Any]] = []
    for node in root.iter("text"):
        text = html.unescape("".join(node.itertext())).replace("\n", " ").strip()
        if text:
            segments.append({"start": _safe_float(node.attrib.get("start")), "duration": _safe_float(node.attrib.get("dur")), "text": text})
    return segments, {"available": True, "language": selected.get("languageCode"), "name": selected.get("languageCode"), "is_auto_generated": selected.get("kind") == "asr"}


def _safe_float(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _which_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    venv_tool = Path(sys.executable).parent / name
    return str(venv_tool) if venv_tool.exists() and os.access(venv_tool, os.X_OK) else None


def _resolve_transcription_backend(backend: str) -> str:
    requested = (backend or DEFAULT_TRANSCRIBE_BACKEND).strip().lower()
    if requested not in {"local", "auto"}:
        raise RuntimeError("Transcription backend must be one of: local, auto")
    if not _which_tool("yt-dlp") or not _which_tool("whisper"):
        raise RuntimeError("Local transcription requires yt-dlp and Whisper CLI. Install with: pip install yt-dlp openai-whisper")
    return "local"


def _run_checked(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=True,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        detail = re.sub(r"\s+", " ", detail)
        if "members-only" in detail.lower() or "join this channel" in detail.lower():
            raise RuntimeError(
                "YouTube audio is not accessible: this appears to be members-only or restricted content. "
                "Use a public video URL or provide accessible captions."
            ) from exc
        if "private video" in detail.lower():
            raise RuntimeError("YouTube audio is not accessible: the video is private.") from exc
        if "sign in" in detail.lower() or "login" in detail.lower():
            raise RuntimeError("YouTube audio is not accessible without sign-in/cookies.") from exc
        raise RuntimeError(f"Transcription command failed: {detail or exc}") from exc


def _transcribe_youtube_audio(video_url: str, backend: str = DEFAULT_TRANSCRIBE_BACKEND, timeout: int = 900) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _resolve_transcription_backend(backend)
    with tempfile.TemporaryDirectory(prefix="agent_adda_youtube_") as tmp:
        workdir = Path(tmp)
        ytdlp = _which_tool("yt-dlp")
        whisper = _which_tool("whisper")
        _run_checked([ytdlp, "--no-playlist", "--quiet", "--no-warnings", "-f", "ba[ext=m4a]/ba", "-o", str(workdir / "audio.%(ext)s"), video_url], timeout=timeout)
        audio = next((p for p in workdir.glob("audio.*") if p.stat().st_size > 0), None)
        if not audio:
            raise RuntimeError("yt-dlp did not produce an audio file")
        _run_checked([whisper, str(audio), "--model", DEFAULT_WHISPER_MODEL, "--language", "en", "--output_format", "json", "--output_dir", str(workdir), "--fp16", "False"], timeout=timeout)
        payload = json.loads(next(workdir.glob("*.json")).read_text(encoding="utf-8"))
    segments = [
        {"start": _safe_float(s.get("start")) or 0.0, "duration": ((_safe_float(s.get("end")) or 0.0) - (_safe_float(s.get("start")) or 0.0)) if s.get("end") is not None else None, "text": re.sub(r"\s+", " ", str(s.get("text") or "")).strip()}
        for s in payload.get("segments", [])
        if str(s.get("text") or "").strip()
    ]
    if not segments and payload.get("text"):
        segments = [{"start": 0.0, "duration": None, "text": re.sub(r"\s+", " ", str(payload.get("text"))).strip()}]
    return segments, {"available": bool(segments), "backend": "local", "model": DEFAULT_WHISPER_MODEL, "source": "audio_stt", "temporary_audio_deleted": True, "stored_full_text": False}


def _latest_video_from_channel(channel: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if channel.get("latest_video_url") or channel.get("sample_video_url"):
        url = str(channel.get("latest_video_url") or channel.get("sample_video_url"))
        ref = parse_youtube_url(url)
        return {"video_id": ref.video_id, "url": ref.canonical_url, "title": channel.get("name") or ref.video_id, "source": "manual"}, None
    channel_id = str(channel.get("channel_id") or "").strip()
    if channel_id:
        try:
            root = ElementTree.fromstring(_http_get(CHANNEL_FEED_URL.format(channel_id=channel_id)))
            ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
            entry = root.find("atom:entry", ns)
            video_id = entry.findtext("yt:videoId", default="", namespaces=ns).strip() if entry is not None else ""
            title = entry.findtext("atom:title", default="", namespaces=ns).strip() if entry is not None else ""
            if video_id:
                return {"video_id": video_id, "url": WATCH_URL.format(video_id=video_id), "title": title or video_id, "source": "rss"}, None
        except Exception:
            pass
    page_url = str(channel.get("channel_url") or "").rstrip("/") + "/videos"
    page = _http_get(page_url)
    match = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', page)
    if match:
        video_id = match.group(1)
        return {"video_id": video_id, "url": WATCH_URL.format(video_id=video_id), "title": "Latest video from channel page", "source": "channel_page"}, None
    return None, "Could not resolve latest video"


def analyze_youtube_channel_latest(selection: str | int, persist: bool = True, max_segments: int = 12, transcribe: bool = False, transcription_backend: str = DEFAULT_TRANSCRIBE_BACKEND) -> dict[str, Any]:
    channel, error = _select_channel(selection)
    if error or not channel:
        return {"status": "error", "error": error or "Could not select channel", "channels": list_youtube_channels().get("channels", [])}
    latest, latest_error = _latest_video_from_channel(channel)
    if latest_error or not latest:
        return {"status": "error", "error": latest_error or "Could not resolve latest video", "channel": channel}
    result = analyze_youtube_video(latest["url"], persist=persist, max_segments=max_segments, transcribe=transcribe, transcription_backend=transcription_backend)
    result["selected_channel"] = {k: channel.get(k) for k in ("id", "name", "category", "language")}
    result["latest_video"] = latest
    result["source_mode"] = "channel_latest"
    return result


def _time_label(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _extract_market_segments(segments: list[dict[str, Any]], max_items: int = 12) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for segment in segments:
        text = re.sub(r"\s+", " ", str(segment.get("text") or "")).strip()
        if not text:
            continue
        score = sum(1 for term in MARKET_TERMS if term in text.lower())
        if score <= 0:
            continue
        scored.append((score, {"timestamp": _time_label(segment.get("start")), "start": segment.get("start"), "symbols": [], "excerpt": text[:280]}))
    scored.sort(key=lambda item: (item[0], item[1].get("start") or 0), reverse=True)
    return [item for _, item in scored[:max_items]]


def _extract_topic_counts(segments: list[dict[str, Any]]) -> dict[str, int]:
    text = " ".join(str(s.get("text") or "") for s in segments).lower()
    topics = {
        "indices": ("nifty", "sensex", "bank nifty", "midcap", "smallcap", "smid"),
        "sectors": ("sector", "banking", "pharma", "health", "it sector", "metal", "auto", "fmcg", "realty"),
        "macro": ("rbi", "fed", "inflation", "rate", "rupee", "crude", "gold", "dollar", "nasdaq", "ai"),
        "earnings": ("earnings", "results", "profit", "revenue", "margin", "guidance"),
        "technicals": ("breakout", "support", "resistance", "moving average", "rsi", "trend", "volatility contraction"),
        "flows": ("fii", "dii", "institutional", "fund flow", "liquidity"),
    }
    return {topic: count for topic, terms in topics.items() if (count := sum(text.count(term) for term in terms)) > 0}


def _derive_market_insights(segments: list[dict[str, Any]], title: str | None, topic_counts: dict[str, int]) -> list[str]:
    text = (" ".join(str(s.get("text") or "") for s in segments) + " " + str(title or "")).lower()
    insights: list[str] = []
    if topic_counts.get("sectors", 0) >= max(3, topic_counts.get("indices", 0)):
        insights.append("Sector selection matters more than broad-index direction; leadership is framed as pocket-specific.")
    if any(term in text for term in ("pharma", "capital market", "health", "healthcare", "small cap")):
        insights.append("Positive pockets mentioned include pharma/healthcare, capital-market names, and select small-cap opportunities.")
    if "it sector" in text:
        insights.append("IT is used as a cautionary valuation example where sentiment can reverse quickly.")
    if any(term in text for term in ("nasdaq", "ai sector", "us tech")):
        insights.append("Global tech/NASDAQ/AI trends are treated as reference points for Indian sector narratives.")
    if "fii" in text:
        insights.append("Institutional-flow context appears relevant; FII absence is framed as shaping market hierarchy.")
    return insights[:6] or ["Market-related commentary detected; validate claims against price, breadth, and sector data."]


def _derive_followups(segments: list[dict[str, Any]], title: str | None) -> list[dict[str, str]]:
    text = (" ".join(str(s.get("text") or "") for s in segments) + " " + str(title or "")).lower()
    followups: list[dict[str, str]] = []
    if any(term in text for term in ("pharma", "health", "healthcare")):
        followups.append({"prompt": "Which pharma and healthcare stocks are leading right now?", "why": "Validate the video's positive healthcare/pharma pocket."})
    if "capital market" in text:
        followups.append({"prompt": "Show Stage 2 capital market stocks with high RS", "why": "Check whether the highlighted capital-market theme has technical confirmation."})
    if any(term in text for term in ("small cap", "smid", "midcap")):
        followups.append({"prompt": "Compare large caps vs midcap and smallcap leadership", "why": "Test the large-cap versus SMID hierarchy."})
    if "it sector" in text:
        followups.append({"prompt": "Assess NIFTY IT sector trend and derating risk", "why": "Confirm the IT caution with trend and RS data."})
    if "fii" in text:
        followups.append({"prompt": "Analyze FII DII flows and India market impact", "why": "The title links market hierarchy to FII absence."})
    if any(term in text for term in ("nasdaq", "ai sector", "us tech")):
        followups.append({"prompt": "Global market assessment for India with NASDAQ and AI read-through", "why": "Global tech is cited as a reference point."})
    return followups[:6] or [{"prompt": "Run sector rotation report", "why": "Validate market-level claims with current breadth."}]


def _persist_artifact(result: dict[str, Any], transcript_hash: str | None) -> str:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / f"{result.get('video_id') or 'unknown'}.json"
    payload = dict(result)
    payload["transcript_hash"] = transcript_hash
    payload["stored_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path.relative_to(ROOT))


def analyze_youtube_video(source: str, persist: bool = True, max_segments: int = 12, transcribe: bool = False, transcription_backend: str = DEFAULT_TRANSCRIBE_BACKEND) -> dict[str, Any]:
    try:
        ref = parse_youtube_url(source)
    except ValueError as exc:
        return {"status": "error", "error": str(exc), "source": source}
    try:
        player = _extract_json_object(_http_get(ref.canonical_url), "ytInitialPlayerResponse")
    except Exception as exc:
        return {"status": "error", "error": f"Could not fetch YouTube watch page: {exc}", "url": ref.canonical_url, "video_id": ref.video_id}
    details = _video_details(player)
    try:
        transcript_segments, transcript_meta = _fetch_transcript_from_player_response(player)
    except Exception as exc:
        transcript_segments, transcript_meta = [], {"available": False, "reason": f"Transcript fetch failed: {exc}"}
    transcription_meta = {"requested": bool(transcribe), "attempted": False, "status": "not_requested"}
    if transcribe and not transcript_segments:
        transcription_meta["attempted"] = True
        try:
            transcript_segments, stt_meta = _transcribe_youtube_audio(ref.canonical_url, transcription_backend)
            transcript_meta = {"available": bool(transcript_segments), "reason": None, "language": "en", "name": "speech-to-text", "is_auto_generated": True, "source": "audio_stt"}
            transcription_meta.update({**stt_meta, "status": "ok" if transcript_segments else "empty"})
        except Exception as exc:
            transcription_meta.update({"available": False, "status": "error", "reason": str(exc), "backend": transcription_backend})
    metadata_segments = []
    if not transcript_segments:
        metadata_text = " ".join(p for p in (details.get("title") or "", str(details.get("short_description") or "")[:4000]) if p).strip()
        if metadata_text:
            metadata_segments = [{"start": ref.start_seconds or 0, "duration": None, "text": metadata_text}]
    evidence_segments = transcript_segments or metadata_segments
    transcript_text = " ".join(str(s.get("text") or "") for s in transcript_segments)
    title = details.get("title") or ref.video_id
    market_segments = _extract_market_segments(evidence_segments, max_items=max_segments)
    segment_source = "audio_stt" if transcript_meta.get("source") == "audio_stt" else "transcript" if transcript_segments else "metadata"
    for segment in market_segments:
        segment["source"] = segment_source
    topic_counts = _extract_topic_counts(evidence_segments)
    result = {
        "status": "ok",
        "video_id": ref.video_id,
        "url": ref.canonical_url,
        "start_seconds": ref.start_seconds,
        "title": title,
        "channel": details.get("channel"),
        "channel_id": details.get("channel_id"),
        "published_at": details.get("published_at"),
        "duration_seconds": details.get("duration_seconds"),
        "transcript": {**transcript_meta, "segment_count": len(transcript_segments), "stored_full_text": False},
        "transcription": transcription_meta,
        "market_topic_counts": topic_counts,
        "market_segments": market_segments,
        "market_insights": _derive_market_insights(evidence_segments, title, topic_counts),
        "suggested_followups": _derive_followups(evidence_segments, title),
        "market_relevance": "HIGH" if len(market_segments) >= 6 else "MEDIUM" if market_segments else "LOW",
        "source_policy": "Captions are used first. Audio speech-to-text runs only for explicit /youtube transcribe requests; temporary audio is deleted and the full transcript is not stored." if transcribe else "Transcript-derived summary when captions are available; otherwise title/description metadata only. Video/audio not downloaded and full transcript not stored.",
    }
    if persist:
        result["artifact_path"] = _persist_artifact(result, hashlib.sha256(transcript_text.encode("utf-8")).hexdigest() if transcript_text else None)
    return result
