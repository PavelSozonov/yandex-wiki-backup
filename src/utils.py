from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def url_to_local_path(url: str, output_dir: Path, is_page: bool = False) -> Path:
    parsed = urlparse(url)
    path = parsed.path
    if is_page:
        if path.endswith('/'):
            path += 'index.html'
        elif not Path(path).suffix:
            path += '.html'
    local = output_dir / path.lstrip('/')
    return local


def hashed_filename(url: str, output_dir: Path) -> Path:
    ext = Path(urlparse(url).path).suffix or '.bin'
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return output_dir / f"{digest}{ext}"
