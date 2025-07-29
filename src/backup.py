import os
import asyncio
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import requests
from dotenv import load_dotenv
from tqdm import tqdm

from .utils import ensure_dir, url_to_path, download_file, rewrite_links


async def fetch_page(context, url: str) -> str:
    page = await context.new_page()
    await page.goto(url)
    await page.wait_for_load_state('networkidle')
    content = await page.content()
    await page.close()
    return content


async def main() -> None:
    load_dotenv()
    root_url = os.getenv("WIKI_ROOT_URL")
    login_url = os.getenv("LOGIN_URL")
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    cookie_string = os.getenv("COOKIE_STRING")
    output_dir = os.getenv("OUTPUT_DIR", "output")
    headless = os.getenv("HEADLESS", "true").lower() == "true"

    if not root_url:
        raise SystemExit("WIKI_ROOT_URL must be set in the environment")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()

        if cookie_string:
            cookies = []
            for pair in cookie_string.split(';'):
                if '=' in pair:
                    name, value = pair.strip().split('=', 1)
                    cookies.append({
                        'name': name.strip(),
                        'value': value.strip(),
                        'domain': urlparse(root_url).hostname,
                        'path': '/'
                    })
            await context.add_cookies(cookies)
        elif username and password and login_url:
            page = await context.new_page()
            await page.goto(login_url)
            try:
                await page.fill('input[name="login"]', username)
            except Exception:
                pass
            await page.fill('input[type="password"]', password)
            await page.press('input[type="password"]', 'Enter')
            await page.wait_for_load_state('networkidle')
            await page.close()
        else:
            page = await context.new_page()
            await page.goto(login_url or root_url)
            if not headless:
                print("\nPlease complete the login in the opened browser window.")
                input("Press Enter here when finished...")
            await page.wait_for_load_state('networkidle')
            await page.close()

        session = requests.Session()
        cookies = await context.cookies()
        for c in cookies:
            session.cookies.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path', '/'))

        to_visit = {root_url}
        visited = set()

        pbar = tqdm(total=0, unit='page')
        while to_visit:
            url = to_visit.pop()
            if url in visited:
                continue
            visited.add(url)
            pbar.set_description(url)
            html = await fetch_page(context, url)
            local_path = url_to_path(url, output_dir)
            rewritten_html, assets = rewrite_links(html, url, output_dir)
            ensure_dir(local_path)
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(rewritten_html)

            for asset_url in assets:
                asset_path = url_to_path(asset_url, output_dir)
                if not os.path.exists(asset_path):
                    try:
                        download_file(session, asset_url, asset_path)
                    except Exception as e:
                        print(f"Failed to download {asset_url}: {e}")

            soup = BeautifulSoup(rewritten_html, 'html.parser')
            for a in soup.find_all('a'):
                href = a.get('href')
                if not href:
                    continue
                abs_href = urljoin(url, href)
                if urlparse(abs_href).netloc == urlparse(root_url).netloc:
                    to_visit.add(abs_href)
            pbar.update(1)
        pbar.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
