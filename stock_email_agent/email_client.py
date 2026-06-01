"""IMAP client for Gmail. Fetches and parses stock-related emails."""
from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Iterable, List, Optional

from .config import EmailConfig


@dataclass
class FetchOptions:
    """Scope of emails to fetch. Combine any of these filters."""
    last_n: Optional[int] = None
    since_days: Optional[int] = None
    unread_only: bool = False
    senders: Optional[List[str]] = None   # extra senders to include
    keywords: Optional[List[str]] = None  # body/subject keywords required


@dataclass
class EmailMessage:
    uid: str
    subject: str
    sender: str
    date: Optional[datetime]
    body_text: str
    body_html: str
    links: List[str] = field(default_factory=list)

    @property
    def short_date(self) -> str:
        return self.date.strftime("%Y-%m-%d %H:%M") if self.date else "unknown"


_LINK_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_bodies(msg: Message) -> tuple[str, str]:
    text_parts: List[str] = []
    html_parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            decoded = ""
        if msg.get_content_type() == "text/html":
            html_parts.append(decoded)
        else:
            text_parts.append(decoded)
    return "\n\n".join(text_parts).strip(), "\n\n".join(html_parts).strip()


def _strip_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def _extract_links(text: str, html: str) -> List[str]:
    links = set(_LINK_RE.findall(text or ""))
    if html:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("http"):
                    links.add(href)
        except Exception:
            links.update(_LINK_RE.findall(html))
    # Drop obvious tracking / unsubscribe noise
    cleaned = []
    skip_hints = ("unsubscribe", "mailto:", "/track/", "list-manage.com", "sendgrid.net")
    for link in links:
        low = link.lower()
        if any(h in low for h in skip_hints):
            continue
        cleaned.append(link)
    return sorted(cleaned)


class GmailIMAPClient:
    def __init__(self, cfg: EmailConfig):
        self.cfg = cfg
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    def __enter__(self) -> "GmailIMAPClient":
        self.cfg.validate()
        self._conn = imaplib.IMAP4_SSL(self.cfg.host, self.cfg.port)
        self._conn.login(self.cfg.user, self.cfg.app_password)
        self._conn.select(self.cfg.mailbox)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._conn is not None:
                self._conn.close()
                self._conn.logout()
        except Exception:
            pass

    def _build_search(self, opts: FetchOptions) -> List[str]:
        criteria: List[str] = []
        if opts.unread_only:
            criteria.append("UNSEEN")
        if opts.since_days:
            since = (datetime.now(timezone.utc) - timedelta(days=opts.since_days)).strftime("%d-%b-%Y")
            criteria.extend(["SINCE", since])
        senders = list(opts.senders or []) + list(self.cfg.sender_allowlist)
        if senders:
            parts: List[str] = []
            for s in senders:
                parts.extend(["FROM", f'"{s}"'])
            if len(senders) > 1:
                # Wrap with OR chain
                wrapped: List[str] = []
                for _ in range(len(senders) - 1):
                    wrapped.append("OR")
                criteria.extend(wrapped + parts)
            else:
                criteria.extend(parts)
        if not criteria:
            criteria = ["ALL"]
        return criteria

    def fetch(self, opts: FetchOptions) -> List[EmailMessage]:
        assert self._conn is not None, "Use as context manager"
        criteria = self._build_search(opts)
        typ, data = self._conn.uid("SEARCH", None, *criteria)
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        # Newest first
        uids = list(reversed(uids))
        if opts.last_n:
            uids = uids[: opts.last_n]

        keywords = [k.lower() for k in (opts.keywords or self.cfg.keyword_filters)]
        results: List[EmailMessage] = []
        for uid in uids:
            typ, msg_data = self._conn.uid("FETCH", uid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            subject = _decode(msg.get("Subject"))
            sender = _decode(msg.get("From"))
            try:
                date = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
            except Exception:
                date = None
            text, html = _extract_bodies(msg)
            body = text or _strip_html(html)
            haystack = f"{subject}\n{body}".lower()
            if keywords and not any(k in haystack for k in keywords):
                continue
            results.append(
                EmailMessage(
                    uid=uid.decode() if isinstance(uid, bytes) else str(uid),
                    subject=subject,
                    sender=sender,
                    date=date,
                    body_text=body,
                    body_html=html,
                    links=_extract_links(body, html),
                )
            )
        return results
