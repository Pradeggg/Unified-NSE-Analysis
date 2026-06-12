"""Broker research source registry definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerSource:
    broker_code: str
    broker_name: str
    source_kind: str
    source_url: str
    access_mode: str
    url_pattern: str = ""
    is_active: bool = True
    notes: str = ""

    def as_insert_params(self) -> tuple[str, str, str, str, str, str, bool, str]:
        return (
            self.broker_code,
            self.broker_name,
            self.source_kind,
            self.source_url,
            self.access_mode,
            self.url_pattern,
            self.is_active,
            self.notes,
        )


BROKER_SOURCES: tuple[BrokerSource, ...] = (
    BrokerSource(
        broker_code="icici",
        broker_name="ICICI Direct",
        source_kind="index_page",
        source_url="https://www.icicidirect.com/mailcontent/co_reports.html",
        access_mode="public",
        url_pattern="https://www.icicidirect.com/mailcontent/idirect_{ticker}_{type}_{period}.pdf",
        notes="Public master coverage index plus direct PDFs.",
    ),
    BrokerSource(
        broker_code="hdfc_hsie",
        broker_name="HDFC Securities / HSIE",
        source_kind="index_page",
        source_url="https://www.hdfcsec.com/research/equity/stock-research-institutional-reports",
        access_mode="public",
        url_pattern="https://www.hdfcsec.com/hsl.docs/{report_title}-HSIE-{timestamp}.pdf",
        notes="Public institutional report index with timestamped PDF links.",
    ),
    BrokerSource(
        broker_code="axis",
        broker_name="Axis Direct",
        source_kind="index_page",
        source_url="https://simplehai.axisdirect.in/app/index.php/insights/reports/fundamental",
        access_mode="public",
        url_pattern="https://simplehai.axisdirect.in/app/index.php/insights/reports/downloadReport/file/{report_title}/type/fundamental",
        notes="Public fundamental research index.",
    ),
    BrokerSource(
        broker_code="axis",
        broker_name="Axis Direct",
        source_kind="index_page",
        source_url="https://simplehai.axisdirect.in/research/research-reports/trading-reports",
        access_mode="public",
        notes="Public technical and trading reports index.",
    ),
    BrokerSource(
        broker_code="sharekhan",
        broker_name="Mirae Asset Sharekhan",
        source_kind="fixed_pdf",
        source_url="https://www.sharekhan.com/MediaGalary/Newsletter/Investoreye.pdf",
        access_mode="public",
        notes="Latest weekly multi-stock Investor's Eye newsletter.",
    ),
    BrokerSource(
        broker_code="sharekhan",
        broker_name="Mirae Asset Sharekhan",
        source_kind="fixed_pdf",
        source_url="https://www.sharekhan.com/MediaGalary/Newsletter/Eagleeye_e.pdf",
        access_mode="public",
        notes="Latest daily technical Eagle Eye newsletter.",
    ),
    BrokerSource(
        broker_code="sharekhan",
        broker_name="Mirae Asset Sharekhan",
        source_kind="fixed_pdf",
        source_url="https://www.sharekhan.com/MediaGalary/Newsletter/DerivativeEye.pdf",
        access_mode="public",
        notes="Latest derivatives newsletter.",
    ),
    BrokerSource(
        broker_code="trendlyne",
        broker_name="Trendlyne Research Reports",
        source_kind="trendlyne_broker",
        source_url="https://trendlyne.com/research-reports/",
        access_mode="partial",
        notes="Discovery metadata only; prefer direct broker PDF evidence when available.",
    ),
)


def active_public_sources() -> tuple[BrokerSource, ...]:
    return tuple(
        source
        for source in BROKER_SOURCES
        if source.is_active and source.access_mode in {"public", "partial"}
    )
