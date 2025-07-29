from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from . import utils


class WikiCrawler:
    def __init__(self, page, output_dir: Path, root_url: str) -> None:
        self.page = page
        self.output_dir = output_dir
        self.root_url = root_url.rstrip('/')
        self.asset_dir = output_dir / "assets"
        utils.ensure_dir(self.asset_dir)
        self.visited: Set[str] = set()
        self.asset_map: Dict[str, Path] = {}
        self.root_domain = urlparse(self.root_url).netloc

    def is_internal(self, url: str) -> bool:
        return urlparse(url).netloc == self.root_domain

    def download_asset(self, url: str) -> Path | None:
        if url in self.asset_map:
            return self.asset_map[url]
        response = self.page.context.request.get(url)
        if not response.ok:
            return None
        dest = utils.hashed_filename(url, self.asset_dir)
        utils.ensure_dir(dest.parent)
        with open(dest, 'wb') as f:
            f.write(response.body())
        self.asset_map[url] = dest
        return dest

    def crawl(self) -> None:
        queue = [self.root_url]
        while queue:
            url = queue.pop(0)
            if url in self.visited:
                continue
            self.visited.add(url)

            print(f"Fetching {url}")
            self.page.goto(url, wait_until="networkidle")
            html = self.page.content()
            local_page = utils.url_to_local_path(url, self.output_dir, is_page=True)
            utils.ensure_dir(local_page.parent)
            soup = BeautifulSoup(html, 'html.parser')

            # Assets
            for tag_name, attr in (('img', 'src'), ('script', 'src'), ('link', 'href')):
                for element in soup.find_all(tag_name):
                    link = element.get(attr)
                    if not link:
                        continue
                    full = urljoin(url, link)
                    asset = self.download_asset(full)
                    if asset:
                        element[attr] = os.path.relpath(asset, local_page.parent)

            # Links
            for element in soup.find_all('a', href=True):
                link = element['href']
                full = urljoin(url, link)
                if self.is_internal(full):
                    queue.append(full)
                    target = utils.url_to_local_path(full, self.output_dir, is_page=True)
                    element['href'] = os.path.relpath(target, local_page.parent)

            with open(local_page, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            print(f"Saved {local_page}")


def authenticate(context, page, root_url: str) -> None:
    cookie = os.getenv('COOKIE')
    username = os.getenv('USERNAME')
    password = os.getenv('PASSWORD')
    if cookie:
        cookies = []
        for item in cookie.split(';'):
            if '=' not in item:
                continue
            name, value = item.split('=', 1)
            cookies.append({"name": name.strip(), "value": value.strip(), "url": root_url})
        context.add_cookies(cookies)
        page.goto(root_url)
    elif username and password:
        login_url = f"https://passport.yandex.com/auth?retpath={root_url}"
        page.goto(login_url)
        page.fill('input[name="login"]', username)
        page.click('button[type="submit"]')
        page.fill('input[name="passwd"]', password)
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
    else:
        page.goto(root_url)


def main() -> None:
    load_dotenv()
    root_url = os.environ.get('WIKI_URL')
    if not root_url:
        raise SystemExit('WIKI_URL is required')
    output_dir = Path(os.environ.get('OUTPUT_DIR', 'output'))
    utils.ensure_dir(output_dir)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        authenticate(context, page, root_url)

        crawler = WikiCrawler(page, output_dir, root_url)
        crawler.crawl()
        browser.close()


if __name__ == '__main__':
    main()
