from __future__ import annotations

from html.parser import HTMLParser

from pydantic import BaseModel


class ParsedPassage(BaseModel):
    text: str
    locator: str
    page: int | None = None


class _PassageHTMLParser(HTMLParser):
    BLOCKS = {"h1", "h2", "h3", "h4", "p", "li", "blockquote", "td", "th"}

    def __init__(self) -> None:
        super().__init__()
        self.ignored_depth = 0
        self.active_block: str | None = None
        self.buffer: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.ignored_depth += 1
        elif tag in self.BLOCKS and self.ignored_depth == 0:
            self._flush()
            self.active_block = tag

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag == self.active_block:
            self._flush()
            self.active_block = None

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth and self.active_block:
            self.buffer.append(data)

    def _flush(self) -> None:
        text = " ".join(" ".join(self.buffer).split())
        if text:
            self.blocks.append(text)
        self.buffer = []


def parse_source(content: bytes, mime_type: str) -> list[ParsedPassage]:
    if mime_type == "application/pdf":
        return _parse_pdf(content)
    decoded = content.decode("utf-8", errors="replace")
    if mime_type == "text/html":
        parser = _PassageHTMLParser()
        parser.feed(decoded)
        parser._flush()
        blocks = parser.blocks
    elif mime_type == "text/plain":
        blocks = [" ".join(block.split()) for block in decoded.split("\n\n") if block.strip()]
    else:
        raise ValueError(f"Unsupported source MIME type: {mime_type}")
    return [
        ParsedPassage(text=block, locator=f"block:{index}")
        for index, block in enumerate(blocks, start=1)
    ]


def _parse_pdf(content: bytes) -> list[ParsedPassage]:
    import fitz

    passages: list[ParsedPassage] = []
    with fitz.open(stream=content, filetype="pdf") as document:
        for page_index, page in enumerate(document, start=1):
            blocks = page.get_text("blocks", sort=True)
            for block_index, block in enumerate(blocks, start=1):
                text = " ".join(str(block[4]).split())
                if text:
                    passages.append(
                        ParsedPassage(
                            text=text,
                            locator=f"page:{page_index}:block:{block_index}",
                            page=page_index,
                        )
                    )
    return passages

