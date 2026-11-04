import re
from markupsafe import Markup, escape

# Regex to detect http, https, and www URLs
URL_PATTERN = re.compile(
    r'(?P<url>(?:https?://|www\.)[^\s<>"\'`()]+(?:\([^\s<>"\'`()]+\)|[^\s`!()\[\]{};:\'\".,<>?«»“”‘’]))',
    re.IGNORECASE
)


def extract_links(text):
    """
    Ekstraksi seluruh tautan URL dari teks menjadi daftar objek:
    [{'url': 'https://...', 'display': '...'}]
    """
    if not text:
        return []
    links = []
    seen = set()
    for match in URL_PATTERN.finditer(str(text)):
        raw_url = match.group('url')
        href = raw_url if raw_url.startswith(('http://', 'https://')) else f'https://{raw_url}'
        if href not in seen:
            seen.add(href)
            links.append({'url': href, 'display': raw_url})
    return links


def autolink(text, truncate_len=None):
    """
    Mengonversi seluruh URL di dalam teks menjadi tag <a> yang aman (kebal XSS).
    Membuka tab baru (target='_blank' rel='noopener noreferrer') dan berikon ↗.
    """
    if not text:
        return ''

    # Sanitasi karakter HTML mentah terlebih dahulu untuk mencegah XSS
    escaped_text = str(escape(text))

    def replace_url(match):
        raw_url = match.group('url')
        href = raw_url if raw_url.startswith(('http://', 'https://')) else f'https://{raw_url}'
        display_text = raw_url
        if truncate_len and len(display_text) > truncate_len:
            display_text = display_text[:truncate_len] + '...'

        return (
            f'<a href="{href}" target="_blank" rel="noopener noreferrer" title="{href}" '
            f'class="text-brand-600 hover:text-brand-800 underline break-all inline-flex items-center gap-0.5 font-medium transition-colors">'
            f'<span>{display_text}</span>'
            f'<svg class="w-3 h-3 inline-block shrink-0 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
            f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path>'
            f'</svg></a>'
        )

    linked_text = URL_PATTERN.sub(replace_url, escaped_text)
    return Markup(linked_text)

