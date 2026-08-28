"""Company-specific website adapters for API-backed investor pages."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from .company_website_indexer import fetch_url


DMART_CONTENT_API = "https://api.dmartindia.com/corporate/content/v1"
DMART_FILE_API = "https://api.dmartindia.com/corporate/content/file/v1"


def get_company_site_adapter(symbol: str, base_url: str = ""):
    clean_symbol = (symbol or "").strip().upper()
    domain = urlparse(base_url or "").netloc.lower()
    if clean_symbol == "DMART" or "dmartindia.com" in domain:
        return DmartInvestorAdapter()
    return None


class DmartInvestorAdapter:
    """Discover official DMart investor documents from the public corporate content API."""

    name = "dmart_investor_api"

    def discover_documents(self, fetcher=fetch_url, limit: int | None = None) -> list[dict[str, Any]]:
        response = fetcher(self.content_api_url())
        if response.get("status") == "error" or int(response.get("status_code", 0) or 0) >= 400:
            return []
        try:
            payload = json.loads(_response_text(response))
        except json.JSONDecodeError:
            return []

        docs: list[dict[str, Any]] = []
        for item in payload if isinstance(payload, list) else []:
            content_id = str(item.get("contentId") or "").strip()
            content = item.get("content") or {}
            category = str(content.get("investorCategoryName") or "").strip()
            for menu in content.get("subMenus") or []:
                period = str(menu.get("name") or menu.get("pageTitle") or "").strip()
                for sub_category in menu.get("subCategories") or []:
                    sub_period = str(sub_category.get("name") or period).strip()
                    for file_info in sub_category.get("files") or []:
                        if not file_info.get("isPublished", True):
                            continue
                        file_id = str(file_info.get("fileId") or "").strip()
                        title = str(file_info.get("fileName") or "").strip()
                        if not content_id or not file_id or not title:
                            continue
                        docs.append(
                            {
                                "source": self.name,
                                "title": title,
                                "url": self.file_url(content_id, file_id, title),
                                "document_type": classify_dmart_document(title, category),
                                "category": category,
                                "period": sub_period or period,
                                "file_id": file_id,
                                "content_id": content_id,
                                "file_type": file_info.get("fileType", ""),
                            }
                        )
                        if limit is not None and len(docs) >= int(limit):
                            return docs
        return docs

    @staticmethod
    def content_api_url() -> str:
        params = {
            "contentPlaceholder": "InvestorRelations_Details",
            "page": "InvestorRelationPage",
            "isPublished": "true",
        }
        return f"{DMART_CONTENT_API}?{urlencode(params)}"

    @staticmethod
    def file_url(content_id: str, file_id: str, title: str) -> str:
        filename = title if title.lower().endswith(".pdf") else f"{title}.pdf"
        return f"{DMART_FILE_API}/{content_id}/{file_id}/{quote(filename)}"


def classify_dmart_document(title: str, category: str = "") -> str:
    text = f"{title} {category}".lower()
    if "annual report" in text:
        return "annual_report"
    if "investor presentation" in text or "presentation" in text:
        return "investor_presentation"
    if "press release" in text:
        return "press_release"
    if "financial result" in text or "results" in text:
        return "results"
    if "transcript" in text or "concall" in text or "earnings call" in text:
        return "concall_transcript"
    if "board meeting" in text:
        return "board_meeting"
    return "investor_update"


def _response_text(response: dict[str, Any]) -> str:
    text = response.get("text")
    if text is not None:
        return str(text)
    content = response.get("content", b"")
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    return str(content)
