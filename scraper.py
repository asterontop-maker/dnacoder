import requests
from typing import Optional

try:
    import trafilatura

    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def fetch_article(url: str) -> Optional[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
    except requests.RequestException:
        return None

    if HAS_TRAFILATURA:
        text = trafilatura.extract(
            html, include_comments=False, include_tables=False
        )
        if text:
            return text

    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
        else:
            paragraphs = soup.find_all("p")

        text = "\n\n".join(
            p.get_text().strip() for p in paragraphs if p.get_text().strip()
        )
        if text:
            return text

    return None


def read_docx(filepath: str) -> Optional[str]:
    try:
        from docx import Document

        doc = Document(filepath)
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return None
