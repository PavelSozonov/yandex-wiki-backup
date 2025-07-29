import os
import re
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup
import requests


def ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def url_to_path(url: str, output_dir: str) -> str:
    """Convert a URL to a safe file path inside output_dir."""
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith('/') or path == '':
        path += 'index.html'
    elif not os.path.splitext(path)[1]:
        path += '.html'
    full_path = os.path.join(output_dir, parsed.netloc, path.lstrip('/'))
    return full_path


def download_file(session: requests.Session, url: str, dest: str) -> None:
    resp = session.get(url, stream=True)
    resp.raise_for_status()
    ensure_dir(dest)
    with open(dest, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def rewrite_links(html: str, base_url: str, output_dir: str) -> tuple[str, list[str]]:
    """Rewrite asset links in HTML and return updated HTML and list of asset URLs."""
    soup = BeautifulSoup(html, 'html.parser')
    assets = []
    tags = {('img', 'src'), ('script', 'src'), ('link', 'href')}
    for tag, attr in tags:
        for element in soup.find_all(tag):
            url = element.get(attr)
            if not url:
                continue
            abs_url = urljoin(base_url, url)
            parsed = urlparse(abs_url)
            if parsed.scheme.startswith('http'):
                asset_path = url_to_path(abs_url, output_dir)
                element[attr] = os.path.relpath(asset_path, os.path.dirname(url_to_path(base_url, output_dir)))
                assets.append(abs_url)
    # Rewrite internal page links
    for element in soup.find_all('a'):
        href = element.get('href')
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        if urlparse(abs_url).netloc == urlparse(base_url).netloc:
            element['href'] = os.path.relpath(
                url_to_path(abs_url, output_dir),
                os.path.dirname(url_to_path(base_url, output_dir))
            )
    return str(soup), assets
