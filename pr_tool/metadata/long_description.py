"""Normalize and validate long-description plain text, Markdown, and HTML."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

_HTML_TAG_RE = re.compile(r'</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^>]*)?>')
_HTML_IMAGE_TAG_RE = re.compile(
    r'</?\s*(?:img|picture|source|svg|video|audio|iframe|object|embed)\b[^>]*>',
    re.IGNORECASE,
)
_MD_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
_BULLET_RE = re.compile(r'^[-*+•]\s+(.+)$')
_NUMBERED_RE = re.compile(r'^\d+[.)]\s+(.+)$')
_QUOTE_RE = re.compile(r'^>\s?(.*)$')
_HR_RE = re.compile(r'^(?:\*{3,}|-{3,}|_{3,})$')
_FENCE_RE = re.compile(r'^```')
_MD_LINK_RE = re.compile(r'(?<!!)\[([^\]]+)\]\(([^)]*)\)')

_ALLOWED_HTML_TAGS = frozenset({
    'a', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'hr', 'i', 'li', 'ol', 'p', 'pre', 'strong', 'ul', 'b',
})
_VOID_HTML_TAGS = frozenset({'br', 'hr'})
_ALLOWED_HTML_ATTRS = {
    'a': frozenset({'href'}),
}
_UNSAFE_HREF_SCHEMES = ('javascript:', 'data:', 'vbscript:')
_INLINE_RE = re.compile(
    r'`([^`]+)`'
    r'|\[([^\]]+)\]\(([^)]+)\)'
    r'|!\[([^\]]*)\]\(([^)]+)\)'
    r'|\*\*\*(.+?)\*\*\*'
    r'|___(.+?)___'
    r'|\*\*(.+?)\*\*'
    r'|__(.+?)__'
    r'|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)'
    r'|(?<![A-Za-z0-9_])_(?!_)(.+?)(?<!_)_(?![A-Za-z0-9_])'
)


def looks_like_html(text: str) -> bool:
    """True when *text* already contains HTML tags."""
    return bool(_HTML_TAG_RE.search(text or ''))


def html_contains_images(text: str) -> bool:
    """True when *text* includes image/media tags or Markdown images."""
    value = text or ''
    return bool(_HTML_IMAGE_TAG_RE.search(value) or _MD_IMAGE_RE.search(value))


def looks_like_markdown(text: str) -> bool:
    """True when *text* uses Markdown structure or inline markup."""
    if not text or looks_like_html(text):
        return False
    for raw_line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = raw_line.strip()
        if (
            _HEADING_RE.match(line)
            or _BULLET_RE.match(line)
            or _NUMBERED_RE.match(line)
            or _QUOTE_RE.match(line)
            or _HR_RE.match(line)
            or _FENCE_RE.match(line)
            or _INLINE_RE.search(raw_line)
        ):
            return True
    return False


def _escape_html(text: str) -> str:
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def _inline_markdown_to_html(text: str) -> str:
    """Convert Markdown emphasis, links, and inline code; leave images as <img>."""
    parts: list[str] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        parts.append(_escape_html(text[pos:match.start()]))
        if match.group(1) is not None:
            parts.append(f'<code>{_escape_html(match.group(1))}</code>')
        elif match.group(2) is not None:
            href = _escape_html(match.group(3).strip())
            parts.append(f'<a href="{href}">{_escape_html(match.group(2))}</a>')
        elif match.group(4) is not None:
            alt = _escape_html(match.group(4))
            src = _escape_html(match.group(5).strip())
            parts.append(f'<img alt="{alt}" src="{src}">')
        elif match.group(6) is not None:
            parts.append(f'<strong><em>{_escape_html(match.group(6))}</em></strong>')
        elif match.group(7) is not None:
            parts.append(f'<strong><em>{_escape_html(match.group(7))}</em></strong>')
        elif match.group(8) is not None:
            parts.append(f'<strong>{_escape_html(match.group(8))}</strong>')
        elif match.group(9) is not None:
            parts.append(f'<strong>{_escape_html(match.group(9))}</strong>')
        elif match.group(10) is not None:
            parts.append(f'<em>{_escape_html(match.group(10))}</em>')
        else:
            parts.append(f'<em>{_escape_html(match.group(11))}</em>')
        pos = match.end()
    parts.append(_escape_html(text[pos:]))
    return ''.join(parts)


def _markdown_to_html(text: str) -> str:
    """Turn Markdown into text HTML. Caller must pass non-empty Markdown."""
    blocks: list[str] = []
    para: list[str] = []
    list_kind: str | None = None
    list_items: list[str] = []
    quote_lines: list[str] = []
    fence_lines: list[str] | None = None

    def flush_para() -> None:
        if para:
            blocks.append(f'<p>{_inline_markdown_to_html(" ".join(para))}</p>')
            para.clear()

    def flush_list() -> None:
        nonlocal list_kind
        if list_kind and list_items:
            items = ''.join(
                f'<li>{_inline_markdown_to_html(item)}</li>' for item in list_items
            )
            blocks.append(f'<{list_kind}>{items}</{list_kind}>')
        list_items.clear()
        list_kind = None

    def flush_quote() -> None:
        if quote_lines:
            inner = normalize_long_description('\n'.join(quote_lines))
            blocks.append(f'<blockquote>{inner}</blockquote>')
            quote_lines.clear()

    def flush_all() -> None:
        flush_para()
        flush_list()
        flush_quote()

    for raw_line in text.split('\n'):
        if fence_lines is not None:
            if _FENCE_RE.match(raw_line.strip()):
                code = _escape_html('\n'.join(fence_lines))
                blocks.append(f'<pre><code>{code}</code></pre>')
                fence_lines = None
            else:
                fence_lines.append(raw_line)
            continue

        line = raw_line.strip()
        if _FENCE_RE.match(line):
            flush_all()
            fence_lines = []
            continue

        quote = _QUOTE_RE.match(line)
        if quote:
            flush_para()
            flush_list()
            quote_lines.append(quote.group(1))
            continue
        flush_quote()

        heading = _HEADING_RE.match(line)
        if heading:
            flush_all()
            level = min(len(heading.group(1)), 6)
            blocks.append(
                f'<h{level}>{_inline_markdown_to_html(heading.group(2).strip())}</h{level}>'
            )
            continue

        if _HR_RE.match(line):
            flush_all()
            blocks.append('<hr>')
            continue

        bullet = _BULLET_RE.match(line)
        numbered = _NUMBERED_RE.match(line)
        if bullet:
            flush_para()
            if list_kind != 'ul':
                flush_list()
                list_kind = 'ul'
            list_items.append(bullet.group(1).strip())
        elif numbered:
            flush_para()
            if list_kind != 'ol':
                flush_list()
                list_kind = 'ol'
            list_items.append(numbered.group(1).strip())
        elif not line:
            flush_all()
        else:
            flush_list()
            para.append(line)
    if fence_lines is not None:
        para.extend(fence_lines)
    flush_all()
    return '\n'.join(blocks)


def normalize_long_description(text: str) -> str:
    """Keep plain text as-is; convert Markdown to HTML; leave HTML unchanged."""
    stripped = (text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not stripped:
        return ''
    if looks_like_html(stripped):
        return stripped
    if looks_like_markdown(stripped):
        return _markdown_to_html(stripped)
    return stripped


def is_safe_href(value: str | None) -> bool:
    """True for http(s)/mailto URLs, in-page fragments, or root-relative paths."""
    href = (value or '').strip()
    if not href or href.lower().startswith(_UNSAFE_HREF_SCHEMES):
        return False
    if href.startswith('#') or href.startswith('/'):
        return True
    parsed = urlparse(href)
    if parsed.scheme == 'mailto':
        return bool(parsed.path)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


class _TextHtmlParser(HTMLParser):
    """Collect allow-list and nesting errors for text-only HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name not in _ALLOWED_HTML_TAGS:
            self.errors.append(f'disallowed HTML tag <{name}>')
            return
        allowed_attrs = _ALLOWED_HTML_ATTRS.get(name, frozenset())
        for attr, value in attrs:
            attr_name = attr.lower()
            if attr_name.startswith('on') or attr_name not in allowed_attrs:
                self.errors.append(f'disallowed HTML attribute {attr_name!r} on <{name}>')
                continue
            if name == 'a' and attr_name == 'href' and not is_safe_href(value):
                self.errors.append('HTML <a href> must be an http(s) or mailto URL')
        if name == 'a' and not any(attr.lower() == 'href' for attr, _unused in attrs):
            self.errors.append('HTML <a> is missing href')
        if name not in _VOID_HTML_TAGS:
            self._stack.append(name)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _VOID_HTML_TAGS:
            return
        if name not in _ALLOWED_HTML_TAGS:
            self.errors.append(f'disallowed HTML tag </{name}>')
            return
        if not self._stack:
            self.errors.append(f'unexpected closing HTML tag </{name}>')
            return
        expected = self._stack.pop()
        if expected != name:
            self.errors.append(
                f'HTML tag mismatch: expected </{expected}>, found </{name}>',
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in _VOID_HTML_TAGS or name in _ALLOWED_HTML_TAGS:
            self.handle_starttag(tag, attrs)
            if name not in _VOID_HTML_TAGS and self._stack and self._stack[-1] == name:
                self._stack.pop()
            return
        self.errors.append(f'disallowed HTML tag <{name}>')

    def handle_comment(self, _data: str) -> None:
        self.errors.append('HTML comments are not allowed')

    def handle_pi(self, _data: str) -> None:
        self.errors.append('HTML processing instructions are not allowed')

    def handle_decl(self, _decl: str) -> None:
        self.errors.append('HTML document declarations are not allowed')

    def close_and_finish(self) -> None:
        self.close()
        if self._stack:
            self.errors.append(f'unclosed HTML tag <{self._stack[-1]}>')


def _html_validation_error(text: str) -> str | None:
    parser = _TextHtmlParser()
    try:
        parser.feed(text)
        parser.close_and_finish()
    except Exception as exc:
        return f'invalid HTML ({exc})'
    if parser.errors:
        return parser.errors[0]
    return None


def _markdown_validation_error(text: str) -> str | None:
    fence_open = False
    for raw_line in text.split('\n'):
        if _FENCE_RE.match(raw_line.strip()):
            fence_open = not fence_open
    if fence_open:
        return 'unclosed Markdown code fence (```)'
    for match in _MD_LINK_RE.finditer(text):
        href = match.group(2).strip()
        if not is_safe_href(href):
            return f'invalid Markdown link URL {href!r} (use http(s) or mailto)'
    return None


def validate_long_description(text: str) -> str | None:
    """Return an error message if Markdown/HTML is invalid; otherwise ``None``.

    Plain text is not rewritten and is considered valid.
    """
    stripped = (text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not stripped:
        return None
    if html_contains_images(stripped):
        return 'images and media tags are not allowed (no <img>, <svg>, <video>, or Markdown images)'
    if looks_like_html(stripped):
        return _html_validation_error(stripped)
    if looks_like_markdown(stripped):
        markdown_error = _markdown_validation_error(stripped)
        if markdown_error:
            return markdown_error
        return _html_validation_error(_markdown_to_html(stripped))
    return None
