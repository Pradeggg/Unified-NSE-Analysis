from __future__ import annotations


AGENT_ADDA_AI_DISCLAIMER_TEXT = (
    "Agent Adda is an AI-assisted research system. It may be incomplete, outdated, or incorrect. "
    "It can miss context, misread filings, or merge data from different periods (standalone vs consolidated). "
    "Always verify all figures and statements from primary sources (exchange filings, annual reports, "
    "investor presentations, and company announcements) before acting."
)


SEBI_STYLE_DISCLAIMER_TEXT = (
    "SEBI DISCLAIMER (research template): Securities markets are subject to market risks. Read all related "
    "documents carefully before investing. Information contained in public issue documents / corporate filings "
    "is the responsibility of the issuer and relevant intermediaries. SEBI does not guarantee the accuracy or "
    "adequacy of those documents and does not endorse any securities or offerings. This report is not an offer, "
    "solicitation, or recommendation to buy/sell/hold any security, and it does not provide investment advice. "
    "If you require regulated advice, consult a SEBI-registered investment adviser or research analyst."
)


def render_disclaimer_block_html() -> str:
    """Return a combined SEBI-style + Agent Adda AI disclaimer block for HTML reports."""
    import html as _html

    return (
        "<div>"
        f"<div><strong>SEBI-style disclaimer</strong></div><div class='sub'>{_html.escape(SEBI_STYLE_DISCLAIMER_TEXT)}</div>"
        "<div style='height:10px'></div>"
        f"<div><strong>Agent Adda AI disclaimer</strong></div><div class='sub'>{_html.escape(AGENT_ADDA_AI_DISCLAIMER_TEXT)}</div>"
        "</div>"
    )

