"""Opt-in, real public-fetch smoke test (no search or LLM credentials required)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.config import Settings
from app.extraction import extract
from app.safety import PublicFetcher


if __name__ == '__main__':
    config = Settings()
    url = 'https://docs.python.org/3/tutorial/datastructures.html'
    final, mime, data = PublicFetcher(config).fetch(url)
    title, passages, warnings = extract(data, mime, final, config.max_pdf_pages)
    assert passages and any('list' in p['text'].lower() for p in passages)
    print({'verified': 'real public HTML retrieval and extraction only', 'url': final, 'title': title,
           'passages': len(passages), 'warnings': warnings, 'search_or_llm_verified': False})
