import io
import re
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .safety import ResourceError


def extract(data: bytes, mime: str, name: str, max_pages: int):
    """Return title, bounded passages with locations, and explicit extraction warnings."""
    warnings = []
    if data.startswith(b'%PDF-'):
        try:
            reader = PdfReader(io.BytesIO(data), strict=False)
            if reader.is_encrypted:
                raise ResourceError('Encrypted PDFs are unsupported; provide an unlocked authorized copy.')
            if len(reader.pages) > max_pages:
                raise ResourceError('PDF exceeds MAX_PDF_PAGES; supply a shorter extract.')
            parts = []
            for index, page in enumerate(reader.pages):
                contents = page.get_contents()
                if contents and len(contents.get_data()) > 8_000_000:
                    raise ResourceError('PDF page content exceeds the extraction limit.')
                text = page.extract_text() or ''
                if len(text.strip()) < 30:
                    warnings.append(f'Page {index + 1} has no usable text; it may be scanned. OCR is not included.')
                else:
                    parts.append((f'page {index + 1}', text))
            if not parts:
                raise ResourceError('PDF has no extractable text; it may be scanned. Supply OCR text or a text-based PDF.')
            title = str((reader.metadata or {}).get('/Title') or name)
        except ResourceError:
            raise
        except Exception:
            raise ResourceError('PDF is damaged or unsupported. Supply a text-based PDF or TXT file.') from None
    elif mime == 'application/pdf' or name.lower().endswith('.pdf'):
        raise ResourceError('File claims to be PDF but does not have a PDF signature.')
    elif mime in ('text/html', 'application/xhtml+xml') or name.lower().endswith(('.html', '.htm')):
        soup = BeautifulSoup(data, 'html.parser')
        title = soup.title.get_text(' ', strip=True) if soup.title else name
        for item in soup(['script', 'style', 'nav', 'footer', 'header', 'form', 'noscript']):
            item.decompose()
        main = soup.find('main') or soup.find('article') or soup.body or soup
        parts = [('main text', main.get_text(' ', strip=True))]
    elif mime == 'text/plain' or name.lower().endswith('.txt'):
        title = name
        try:
            parts = [('text', data.decode('utf-8-sig'))]
        except UnicodeError:
            raise ResourceError('Text files must be UTF-8 encoded.') from None
    else:
        raise ResourceError('Unsupported format. Supply public HTML, UTF-8 TXT or a text-based PDF.')
    chunks = []
    for location, text in parts:
        text = re.sub(r'\s+', ' ', text).strip()
        for offset in range(0, min(len(text), 60000), 1600):
            chunks.append({'location': f'{location}, characters {offset + 1}-{min(offset + 1800, len(text))}', 'text': text[offset:offset + 1800]})
        if len(text) > 60000:
            warnings.append(f'{location}: text truncated at 60,000 characters.')
    if not chunks or sum(len(c['text']) for c in chunks) < 30:
        raise ResourceError('Source contains insufficient extractable text.')
    if len(chunks) > 100:
        warnings.append('Extraction limited to the first 100 passages.')
    return title[:300], chunks[:100], warnings
