from __future__ import annotations

import argparse
import shlex
from datetime import datetime


def parse_voice_briefing_args(command_args: str | list[str]) -> argparse.Namespace:
    tokens = shlex.split(command_args) if isinstance(command_args, str) else list(command_args)
    parser = argparse.ArgumentParser(prog="/voice", add_help=False)
    parser.add_argument("items", nargs="*")
    parser.add_argument("--no-tts", dest="want_tts", action="store_false")
    parser.add_argument("--no-audio", dest="want_tts", action="store_false")
    parser.add_argument("--no-play", dest="auto_play", action="store_false")
    parser.add_argument("--no-autoplay", dest="auto_play", action="store_false")
    parser.set_defaults(want_tts=True, auto_play=True)
    ns = parser.parse_args(tokens)

    date_arg = None
    for item in ns.items:
        lowered = item.lower()
        if lowered in ("script", "txt", "text"):
            ns.want_tts = False
        elif _is_date_arg(item):
            date_arg = item
        else:
            parser.error(f"unknown /voice argument: {item}")
    ns.date = date_arg
    return ns


def parse_ask_voice_args(command_args: str | list[str]) -> argparse.Namespace:
    tokens = shlex.split(command_args) if isinstance(command_args, str) else list(command_args)
    parser = argparse.ArgumentParser(prog="/ask-voice", add_help=False)
    parser.add_argument("--audio-file", default="")
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--no-audio", dest="want_audio", action="store_false")
    parser.add_argument("--no-play", dest="auto_play", action="store_false")
    parser.add_argument("--voice", default="cedar")
    parser.set_defaults(want_audio=True, auto_play=True)
    return parser.parse_args(tokens)


def parse_voice_live_args(command_args: str | list[str]) -> argparse.Namespace:
    tokens = shlex.split(command_args) if isinstance(command_args, str) else list(command_args)
    parser = argparse.ArgumentParser(prog="/voice-live", add_help=False)
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--seconds", type=int, default=12)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--no-audio", dest="want_audio", action="store_false")
    parser.add_argument("--no-play", dest="auto_play", action="store_false")
    parser.add_argument("--voice", default="cedar")
    parser.set_defaults(want_audio=True, auto_play=True)
    return parser.parse_args(tokens)


def _is_date_arg(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False
