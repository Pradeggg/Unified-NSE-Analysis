from knowledge_base import chunker


def test_chunk_document_sniffs_pdf_magic_when_download_name_is_aspx(monkeypatch, tmp_path):
    pdf_path = tmp_path / "annpdfopen.aspx"
    pdf_path.write_bytes(b"%PDF-1.7\nfixture")

    monkeypatch.setattr(chunker, "_pdf_to_pages", lambda path: [(1, "Readable filing text")])

    def fail_if_html_parser_is_used(path):
        raise AssertionError("valid PDF was routed through the HTML parser")

    monkeypatch.setattr(chunker, "_html_to_text", fail_if_html_parser_is_used)

    chunks = list(
        chunker.chunk_document(
            {
                "path": str(pdf_path),
                "kind": "html",
                "source_id": "fixture",
            }
        )
    )

    assert [item["text"] for item in chunks] == ["Readable filing text"]
    assert chunks[0]["kind"] == "pdf"


def test_chunk_document_accepts_pdf_header_after_leading_bytes(monkeypatch, tmp_path):
    pdf_path = tmp_path / "download.aspx"
    pdf_path.write_bytes(b"\xef\xbb\xbf\n%PDF-1.7\nfixture")
    monkeypatch.setattr(chunker, "_pdf_to_pages", lambda path: [(1, "Readable filing text")])
    monkeypatch.setattr(
        chunker,
        "_html_to_text",
        lambda path: (_ for _ in ()).throw(AssertionError("PDF routed through HTML parser")),
    )

    chunks = list(chunker.chunk_document({"path": str(pdf_path), "kind": "html"}))

    assert chunks[0]["kind"] == "pdf"


def test_chunk_document_keeps_real_html_on_html_parser(monkeypatch, tmp_path):
    html_path = tmp_path / "filing.aspx"
    html_path.write_text("<html><body>Filing text</body></html>")
    monkeypatch.setattr(chunker, "_html_to_text", lambda path: "Filing text")
    monkeypatch.setattr(
        chunker,
        "_pdf_to_pages",
        lambda path: (_ for _ in ()).throw(AssertionError("HTML routed through PDF parser")),
    )

    chunks = list(chunker.chunk_document({"path": str(html_path), "kind": "html"}))

    assert [item["text"] for item in chunks] == ["Filing text"]
    assert chunks[0]["kind"] == "html"


def test_chunk_document_does_not_treat_pdf_literal_in_html_body_as_magic(monkeypatch, tmp_path):
    html_path = tmp_path / "filing.aspx"
    html_path.write_text("<html><body>Documentation mentions %PDF-1.7 here</body></html>")
    monkeypatch.setattr(chunker, "_html_to_text", lambda path: "Readable HTML filing")
    monkeypatch.setattr(
        chunker,
        "_pdf_to_pages",
        lambda path: (_ for _ in ()).throw(AssertionError("HTML routed through PDF parser")),
    )

    chunks = list(chunker.chunk_document({"path": str(html_path), "kind": "html"}))

    assert [item["text"] for item in chunks] == ["Readable HTML filing"]
    assert chunks[0]["kind"] == "html"
