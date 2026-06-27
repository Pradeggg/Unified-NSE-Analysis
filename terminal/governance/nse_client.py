from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin


class NSEJsonClient:
    BASE_URL = "https://www.nseindia.com"

    def __init__(self, session: Any = None, seed_delay_s: float = 0.3, timeout_s: float = 12.0):
        if session is None:
            import requests

            session = requests.Session()
        self.session = session
        self.seed_delay_s = seed_delay_s
        self.timeout_s = timeout_s
        self.seeded = False
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Referer": f"{self.BASE_URL}/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                ),
            }
        )

    def seed(self) -> None:
        if self.seeded:
            return
        try:
            response = self.session.get(self.BASE_URL, timeout=self.timeout_s)
            self.seeded = getattr(response, "status_code", None) == 200
            if self.seed_delay_s:
                time.sleep(self.seed_delay_s)
        except Exception:
            pass

    def get_json(self, path: str, params: dict[str, Any] | None = None, retries: int = 1) -> dict[str, Any]:
        self.seed()
        url = path if path.startswith(("http://", "https://")) else urljoin(f"{self.BASE_URL}/", path.lstrip("/"))
        last_error = ""
        last_status_code = None
        attempts = max(1, retries + 1)

        for attempt in range(attempts):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_s)
                status_code = getattr(response, "status_code", None)
                last_status_code = status_code
                if status_code == 200:
                    return {"status": "ok", "json": response.json(), "status_code": status_code, "url": url}
                last_error = f"HTTP {status_code}"
            except Exception as exc:
                last_error = str(exc)

            if attempt < attempts - 1:
                time.sleep(0.2 * (attempt + 1))

        return {"status": "error", "json": None, "error": last_error, "status_code": last_status_code, "url": url}
