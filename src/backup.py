from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Set
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from . import utils


class WikiCrawler:
    def __init__(self, page, output_dir: Path, root_url: str, request_context=None, use_cache: bool = True) -> None:
        self.page = page
        self.output_dir = output_dir
        self.root_url = root_url.rstrip('/')
        self.asset_dir = output_dir / "assets"
        utils.ensure_dir(self.asset_dir)
        self.visited: Set[str] = set()
        self.asset_map: Dict[str, Path] = {}
        self.root_domain = urlparse(self.root_url).netloc
        self.request_context = request_context or page.context.request
        self.use_cache = use_cache
        
        # Кэш для избежания повторной обработки
        self.cache_file = self.output_dir / ".crawler_cache.json"
        self.processed_pages: Set[str] = set()
        self.failed_urls: Set[str] = set()
        
        # Загружаем кэш если он существует и совместим
        if self.use_cache:
            self.load_cache()
        # Список доменов которые считаются внутренними (включая CDN)
        self.internal_domains = {
            self.root_domain,
            'yastatic.net',
            'avatars.mds.yandex.net', 
            'forms.yandex.ru',
            'mc.yandex.ru',
            'yandex.ru',
            'storage.yandexcloud.net'  # Добавляем Yandex Cloud Storage
        }
        # URL которые нужно игнорировать
        self.ignore_patterns = [
            r'\/metrika\/',
            r'\/watch\/',
            r'\.json$',
            r'api\/',
            r'ajax\/',
            r'#',
            r'javascript:',
            r'mailto:',
            r'tel:'
        ]

    def load_cache(self) -> None:
        """Загружает кэш из файла"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                    # Проверяем совместимость кэша с новой структурой
                    cache_version = cache_data.get('version', 1)
                    if cache_version < 2:  # Новая версия для структуры директорий
                        print(f"  ⚠️  Старый кэш несовместим с новой структурой. Очищаем кэш.")
                        return
                    
                    self.processed_pages = set(cache_data.get('processed_pages', []))
                    self.failed_urls = set(cache_data.get('failed_urls', []))
                    self.asset_map = {url: Path(path) for url, path in cache_data.get('asset_map', {}).items()}
                print(f"  💾 Загружен кэш v{cache_version}: {len(self.processed_pages)} страниц, {len(self.asset_map)} ресурсов")
        except Exception as e:
            print(f"  ⚠️  Ошибка при загрузке кэша: {e}")

    def save_cache(self) -> None:
        """Сохраняет кэш в файл"""
        try:
            cache_data = {
                'version': 2,  # Версия для структуры директорий
                'processed_pages': list(self.processed_pages),
                'failed_urls': list(self.failed_urls),
                'asset_map': {url: str(path) for url, path in self.asset_map.items()}
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            print(f"  💾 Сохранен кэш v2: {len(self.processed_pages)} страниц, {len(self.asset_map)} ресурсов")
        except Exception as e:
            print(f"  ⚠️  Ошибка при сохранении кэша: {e}")

    def should_ignore_url(self, url: str) -> bool:
        """Проверяет, нужно ли игнорировать URL"""
        for pattern in self.ignore_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    def is_internal(self, url: str) -> bool:
        """Проверяет является ли URL внутренним"""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Проверяем домен
        if domain in self.internal_domains:
            return True
            
        # Проверяем поддомены основного домена
        if domain.endswith('.' + self.root_domain):
            return True
            
        return False

    def is_wiki_page(self, url: str) -> bool:
        """Проверяет является ли URL страницей wiki"""
        parsed = urlparse(url)
        
        # Только страницы с основного домена wiki считаются страницами
        if parsed.netloc != self.root_domain:
            return False
            
        # Игнорируем служебные пути
        if self.should_ignore_url(url):
            return False
            
        path = parsed.path.lower()
        # Игнорируем файлы со статическим содержимым
        static_extensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf']
        if any(path.endswith(ext) for ext in static_extensions):
            return False
            
        return True

    def process_css_content(self, css_content: str, css_url: str) -> str:
        """Обрабатывает содержимое CSS файла, заменяя URL ресурсов"""
        def replace_url(match):
            url = match.group(1).strip('\'"')
            if url.startswith('data:') or url.startswith('#'):
                return match.group(0)
                
            full_url = urljoin(css_url, url)
            asset = self.download_asset(full_url)
            if asset:
                # Определяем правильный относительный путь
                css_local_path = utils.url_to_local_path(css_url, self.output_dir)
                
                # Для CSS/JS файлов от yastatic используем абсолютные пути
                parsed_url = urlparse(full_url)
                if (parsed_url.path.endswith(('.css', '.js')) and 
                    'yastatic.net/s3/cloud' in full_url and 
                    'static/freeze' in full_url):
                    # CSS находится в assets/, используем абсолютный путь от корня сервера
                    return f'url("/assets/{asset.name}")'
                else:
                    # Для остальных ресурсов используем обычный относительный путь
                    rel_path = os.path.relpath(asset, css_local_path.parent)
                    return f'url("{rel_path}")'
            return match.group(0)
            
        # Заменяем все url() в CSS
        return re.sub(r'url\s*\(\s*([^)]+)\s*\)', replace_url, css_content)

    def process_js_content(self, js_content: str, js_url: str) -> str:
        """Обрабатывает содержимое JavaScript файла, заменяя webpack пути"""
        # Более безопасное удаление source map URL - только в конце файла
        # Удаляем только если это последняя строка и содержит sourceMappingURL
        lines = js_content.split('\n')
        if lines and lines[-1].strip().startswith('//# sourceMappingURL='):
            lines = lines[:-1]
        
        # Удаляем пустые строки в конце
        while lines and not lines[-1].strip():
            lines.pop()
        
        # Добавляем одну пустую строку в конце для корректности
        lines.append('')
        js_content = '\n'.join(lines)
        
        # Безопасная обработка - только основные замены
        patterns = [
            # Set public path with trailing slash
            (r'f\.p\s*=\s*[\'"]/assets/?[\'"]', 'f.p="/assets/"'),
            # Remove /assets/ prefix from chunk filenames (js/css)
            (r'[\'"]/assets/([^\'\"]+\.(?:js|css))[\'"]', r'"\1"'),
            # Remove /assets/ prefix from any other asset references
            (r'[\'"]/assets/([^\'\"]+)[\'"]', r'"\1"'),
            # publicPath - dynamic
            (r'f\.p\s*=\s*e\s*\+\s*[\'"]\.\.\/[\'"]', 'f.p="/assets/"'),
            # publicPath - exact
            (r'f\.p\s*=\s*[\'"][^\'\"]*yastatic\.net/s3/cloud/(?:wiki|auth)/static/freeze/[\'"];', 'f.p="/assets/";'),
            # __webpack_public_path__ - exact
            (r'__webpack_public_path__\s*=\s*[\'"]https://yastatic\.net/s3/cloud/(?:wiki|auth)/static/freeze/[\'"]', '__webpack_public_path__="/assets/"'),
            # Remove js/ and css/ prefixes from chunk paths
            (r'[\'"]js\/([^\'\"]+\.js)[\'"]', r'"\1"'),
            (r'[\'"]css\/([^\'\"]+\.css)[\'"]', r'"\1"'),
            # Replace yastatic URLs with /assets/
            (r'[\'"]https://yastatic\.net/s3/cloud/(?:wiki|auth)/static/freeze/', '"/assets/'),
        ]
        
        for pattern, replacement in patterns:
            js_content = re.sub(pattern, replacement, js_content)
            
        return js_content

    def download_asset(self, url: str) -> Path | None:
        """Загружает ассет и возвращает локальный путь"""
        if url in self.asset_map:
            return self.asset_map[url]
        
        # Проверяем, не был ли URL уже неудачным
        if url in self.failed_urls:
            return None
            
        dest = utils.hashed_filename(url, self.asset_dir)
        
        # Проверяем кэш - если файл уже существует и включено кэширование
        if self.use_cache and dest.exists() and dest.stat().st_size > 0:
            print(f"  💾 Из кэша: {dest.name}")
            self.asset_map[url] = dest
            return dest
            
        try:
            print(f"  📥 Загружается: {url}")
            
            # Используем отдельный request_context если он есть, иначе контекст страницы
            if self.request_context:
                response = self.request_context.get(url)
            else:
                response = self.page.context.request.get(url, ignore_https_errors=True)
            
            if not response.ok:
                print(f"  ❌ Не удалось загрузить {url}: HTTP {response.status}")
                self.failed_urls.add(url)
                return None
                
            utils.ensure_dir(dest.parent)
            content = response.body()
            
            # Если это CSS файл, обрабатываем его содержимое
            if url.endswith('.css'):
                try:
                    css_content = content.decode('utf-8')
                    processed_css = self.process_css_content(css_content, url)
                    content = processed_css.encode('utf-8')
                    print(f"  🎨 Обработан CSS: {url}")
                except UnicodeDecodeError:
                    print(f"  ⚠️  Не удалось декодировать CSS файл {url}")
            elif url.endswith('.js'):
                try:
                    js_content = content.decode('utf-8')
                    processed_js = self.process_js_content(js_content, url)
                    content = processed_js.encode('utf-8')
                    print(f"  🎨 Обработан JS: {url}")
                except UnicodeDecodeError:
                    print(f"  ⚠️  Не удалось декодировать JS файл {url}")
            
            with open(dest, 'wb') as f:
                f.write(content)
                
            self.asset_map[url] = dest
            print(f"  ✅ Сохранен: {dest.name}")
            return dest
            
        except Exception as e:
            print(f"  ❌ Ошибка при загрузке {url}: {e}")
            # Не прерываем выполнение, просто пропускаем ресурс
            return None

    def crawl(self) -> None:
        """Основной метод обхода"""
        queue = [self.root_url]
        processed_pages = 0
        max_pages = 1000  # Ограничение для предотвращения бесконечного обхода
        
        print(f"🚀 Начинаем обход с {self.root_url}")
        print(f"📁 Результат будет сохранен в {self.output_dir}")
        print(f"♻️  Существующие файлы будут перезаписаны")
        
        while queue and processed_pages < max_pages:
            url = queue.pop(0)
            if url in self.visited or self.should_ignore_url(url):
                continue
                
            self.visited.add(url)
            local_page = utils.url_to_local_path(url, self.output_dir, is_page=True)
            
            # Проверяем кэш страницы - если файл уже существует и включено кэширование
            if (self.use_cache and local_page.exists() and 
                local_page.stat().st_size > 0 and url in self.processed_pages):
                print(f"\n💾 Страница из кэша ({processed_pages + 1}/{max_pages}): {url}")
                processed_pages += 1
                continue
            
            try:
                print(f"\n📄 Обрабатывается ({processed_pages + 1}/{max_pages}): {url}")
                self.page.goto(url, wait_until="networkidle", timeout=30000)
                html = self.page.content()
                
                utils.ensure_dir(local_page.parent)
                soup = BeautifulSoup(html, 'html.parser')

                # Обработка ассетов (изображения, скрипты, стили)
                asset_count = 0
                for tag_name, attr in [('img', 'src'), ('script', 'src'), ('link', 'href')]:
                    for element in soup.find_all(tag_name):
                        link = element.get(attr)
                        if not link:
                            continue
                            
                        full = urljoin(url, link)
                        
                        # Отладка для изображений
                        if tag_name == 'img' and ('.png' in link or '.jpg' in link or '.jpeg' in link):
                            print(f"  🖼️  Изображение: {link} -> {full}")
                        
                        # Пропускаем внешние ресурсы которые не нужно скачивать
                        if not self.is_internal(full):
                            if tag_name == 'img':
                                print(f"  ❌ Внешнее изображение пропущено: {full}")
                            continue
                            
                        # For images, always rewrite to /assets/<hash>.<ext>
                        if tag_name == 'img' and self.is_internal(full):
                            asset = self.download_asset(full)
                            if asset:
                                element[attr] = '/assets/' + asset.name
                                continue
                        # For scripts and links, keep existing logic
                        asset = self.download_asset(full)
                        if asset:
                            # Для CSS/JS файлов от yastatic используем абсолютные пути  
                            parsed_url = urlparse(full)
                            if (parsed_url.path.endswith(('.css', '.js')) and 
                                'yastatic.net/s3/cloud' in full and 
                                'static/freeze' in full):
                                # Эти файлы сохранены под оригинальными именами в assets/ - используем абсолютные пути
                                element[attr] = f"/assets/{asset.name}"
                            elif parsed_url.path.endswith(('.css', '.js')) and asset.parent.name == 'assets':
                                # Для всех остальных CSS/JS файлов в assets используем абсолютные пути
                                element[attr] = f"/assets/{asset.name}"
                            else:
                                # Для всех остальных файлов (включая изображения) используем абсолютные пути от сервера
                                relative_to_output = os.path.relpath(asset, self.output_dir)
                                element[attr] = "/" + relative_to_output.replace(os.sep, "/")
                                if tag_name == 'img':
                                    print(f"  🖼️  Путь к изображению обновлен: {link} -> /{relative_to_output.replace(os.sep, '/')}")
                            asset_count += 1
                        else:
                            if tag_name == 'img':
                                print(f"  ❌ Изображение не скачалось: {full}")

                # Обработка ссылок
                new_links = []
                link_count = 0
                for element in soup.find_all('a', href=True):
                    link = element['href']
                    full = urljoin(url, link)
                    
                    if self.is_wiki_page(full) and full not in self.visited:
                        new_links.append(full)
                        target = utils.url_to_local_path(full, self.output_dir, is_page=True)
                        relative_to_output = os.path.relpath(target, self.output_dir)
                        # Always add /index.html for wiki pages
                        if not relative_to_output.endswith('index.html'):
                            relative_to_output = relative_to_output.rstrip('/') + '/index.html'
                        if relative_to_output.startswith('wiki.yandex.ru/'):
                            relative_to_output = relative_to_output[len('wiki.yandex.ru/'):]
                        # Pretty URL: strip /index.html from the end
                        if relative_to_output.endswith('/index.html'):
                            relative_to_output = relative_to_output[:-len('/index.html')]
                        element['href'] = '/' + relative_to_output.replace(os.sep, '/')
                        link_count += 1
                    elif self.is_internal(full):
                        target = utils.url_to_local_path(full, self.output_dir)
                        relative_to_output = os.path.relpath(target, self.output_dir)
                        if relative_to_output.startswith('wiki.yandex.ru/'):
                            relative_to_output = relative_to_output[len('wiki.yandex.ru/'):]
                        element['href'] = '/' + relative_to_output.replace(os.sep, '/')

                # Исправляем JavaScript пути
                js_fixes = 0
                for script in soup.find_all('script'):
                    if script.string:
                        content = script.string
                        original_content = content
                        
                        # Исправляем __PUBLIC_PATH__ - используем абсолютные пути без trailing slash
                        if '__PUBLIC_PATH__' in content:
                            content = content.replace(
                                'https://yastatic.net/s3/cloud/wiki/static/freeze/',
                                '/assets'
                            ).replace(
                                'https://yastatic.net/s3/cloud/auth/static/freeze/',
                                '/assets'
                            )
                        
                        # Исправляем webpack publicPath и чанки - абсолютные пути без trailing slash
                        webpack_patterns = [
                            # webpack publicPath
                            (r'publicPath\s*[:=]\s*[\'"]https://yastatic\.net/s3/cloud/wiki/static/freeze/[\'"]', 
                             'publicPath: "/assets"'),
                            (r'publicPath\s*[:=]\s*[\'"]https://yastatic\.net/s3/cloud/auth/static/freeze/[\'"]', 
                             'publicPath: "/assets"'),
                            
                            # __webpack_public_path__
                            (r'__webpack_public_path__\s*=\s*[\'"]https://yastatic\.net/s3/cloud/wiki/static/freeze/[\'"]',
                             '__webpack_public_path__ = "/assets"'),
                            (r'__webpack_public_path__\s*=\s*[\'"]https://yastatic\.net/s3/cloud/auth/static/freeze/[\'"]',
                             '__webpack_public_path__ = "/assets"'),
                            
                            # Прямые URL в чанках - абсолютные пути
                            (r'[\'"]https://yastatic\.net/s3/cloud/wiki/static/freeze/',
                             '"/assets/'),
                            (r'[\'"]https://yastatic\.net/s3/cloud/auth/static/freeze/',
                             '"/assets/'),
                        ]
                        
                        for pattern, replacement in webpack_patterns:
                            content = re.sub(pattern, replacement, content)
                        
                        # Исправляем JSON данные с путями wiki в embedded JavaScript
                        if '"wikiPath":' in content:
                            # Remove /wiki.yandex.ru/ from JSON navigation paths and add /index.html, then strip /index.html for pretty URLs
                            content = re.sub(r'"/wiki\.yandex\.ru/([^"*?)(?<!index\.html)"', lambda m: f'"/{m.group(1).rstrip("/")}/index.html"', content)
                            content = re.sub(r'/index\.html"', '"', content)
                            print(f"  🔗 Исправлены JSON пути в скрипте (pretty URLs)")
                        
                        # Если контент изменился, обновляем скрипт
                        if content != original_content:
                            script.string = content
                            js_fixes += 1

                with open(local_page, 'w', encoding='utf-8') as f:
                    f.write(str(soup))
                
                # Помечаем страницу как обработанную для кэширования
                self.processed_pages.add(url)
                    
                print(f"  ✅ Сохранено: {local_page}")
                print(f"  📊 Ассетов: {asset_count}, Ссылок: {link_count}, JS исправлений: {js_fixes}")
                
                # Добавляем новые ссылки в очередь
                if new_links:
                    print(f"  🔗 Найдено новых ссылок: {len(new_links)}")
                    queue.extend(new_links)
                processed_pages += 1
                
            except Exception as e:
                print(f"  ❌ Ошибка при обработке {url}: {e}")
                self.failed_urls.add(url)
                # Продолжаем обработку следующих страниц
                continue
        
        # Сохраняем кэш
        if self.use_cache:
            self.save_cache()
                
        print(f"\n🎉 Обход завершен!")
        print(f"📊 Статистика:")
        print(f"  • Обработано страниц: {processed_pages}")
        print(f"  • Найдено ассетов: {len(self.asset_map)}")
        print(f"  • Всего посещено URL: {len(self.visited)}")


def authenticate(context, page, root_url: str) -> None:
    """Аутентификация пользователя"""
    method = os.getenv("AUTH_METHOD", "cookie").lower()
    cookie = os.getenv("COOKIE")
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")

    print(f"🔐 Аутентификация методом: {method}")

    if method == "cookie" and cookie:
        cookies = []
        for item in cookie.split(";"):
            if "=" not in item:
                continue
            name, value = item.split("=", 1)
            cookies.append({"name": name.strip(), "value": value.strip(), "url": root_url})
        context.add_cookies(cookies)
        print(f"  ✅ Добавлено cookie: {len(cookies)} шт.")
        page.goto(root_url)
    elif method == "credentials" and username and password:
        print(f"  🔑 Вход с учетными данными...")
        login_url = f"https://passport.yandex.com/auth?retpath={root_url}"
        page.goto(login_url)
        page.fill("input[name='login']", username)
        page.click("button[type='submit']")
        page.wait_for_selector("input[name='passwd']", timeout=10000)
        page.fill("input[name='passwd']", password)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        print(f"  ✅ Вход выполнен")
    else:
        print(f"  ⚠️  Аутентификация не настроена, переходим без входа")
        page.goto(root_url)

    # Проверяем, не попали ли мы на страницу авторизации
    page_title = page.title()
    if "Auth" in page_title or "Вход" in page_title or "Login" in page_title:
        print(f"  ⚠️  Обнаружена страница авторизации: '{page_title}'")
        
        # Пытаемся найти ссылку на wiki или перейти на главную
        try:
            # Ждем загрузки и пробуем найти ссылки на wiki
            page.wait_for_timeout(2000)
            
            # Пробуем разные варианты URL
            wiki_urls = [
                root_url.replace('/homepage', ''),
                root_url.replace('/homepage', '/') + 'pages',
                root_url.replace('/homepage', '/') + 'wiki',
                'https://wiki.yandex-team.ru',
                'https://wiki.yandex.ru'
            ]
            
            for wiki_url in wiki_urls:
                if wiki_url != root_url:
                    try:
                        print(f"  🔄 Пробую перейти на: {wiki_url}")
                        page.goto(wiki_url, wait_until="networkidle", timeout=15000)
                        new_title = page.title()
                        
                        # Проверяем, не авторизационная ли это страница
                        if not any(word in new_title for word in ["Auth", "Вход", "Login"]):
                            print(f"  ✅ Успешно перешли на wiki: '{new_title}'")
                            return
                            
                    except Exception as e:
                        print(f"  ❌ Не удалось перейти на {wiki_url}: {e}")
                        continue
                        
            print(f"  ⚠️  Остались на странице авторизации. Возможно нужны корректные учетные данные.")
            
        except Exception as e:
            print(f"  ❌ Ошибка при попытке перехода с страницы авторизации: {e}")


def main() -> None:
    """Главная функция"""
    load_dotenv()
    root_url = os.environ.get('WIKI_URL')
    if not root_url:
        raise SystemExit('❌ WIKI_URL обязателен в переменных окружения')
    
    output_dir = Path(os.environ.get('OUTPUT_DIR', 'output'))
    ignore_ssl = os.getenv("IGNORE_SSL_ERRORS", "false").lower() in ("1", "true", "yes")
    
    print(f"🌐 Wiki URL: {root_url}")
    print(f"📁 Папка вывода: {output_dir}")
    print(f"🔒 Игнорировать SSL: {ignore_ssl}")
    
    utils.ensure_dir(output_dir)

    with sync_playwright() as p:
        # Улучшенные настройки браузера для обхода SSL ошибок
        browser = p.firefox.launch(
            headless=True,
            args=[
                '--ignore-certificate-errors-spki-list',
                '--ignore-certificate-errors',
                '--ignore-ssl-errors',
                '--allow-running-insecure-content'
            ]
        )
        
        # Создаем контекст с настройками SSL
        context = browser.new_context(
            ignore_https_errors=ignore_ssl,
            bypass_csp=True,  # Обход Content Security Policy
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Создаем отдельный APIRequestContext с правильными SSL настройками
        request_context = None
        if ignore_ssl:
            context.set_extra_http_headers({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                "sec-ch-ua-mobile": "?0", 
                "sec-ch-ua-platform": '"macOS"'
            })
            
            # Получаем cookies из браузерного контекста
            page = context.new_page()
            page.goto(root_url, wait_until="networkidle", timeout=30000)
            authenticate(context, page, root_url)
            
            # Получаем все cookies после авторизации
            cookies = context.cookies()
            
            # Создаем новый APIRequestContext с cookie и заголовками
            print("🔧 Создаем APIRequestContext с cookie и заголовками...")
            request_context = p.request.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                    "Upgrade-Insecure-Requests": "1",
                    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"'
                }
            )
            
            # Добавляем cookies в request context через storage_state
            if cookies:
                # Преобразуем cookies в формат storage_state
                storage_state = {
                    "cookies": [
                        {
                            "name": cookie["name"],
                            "value": cookie["value"],
                            "domain": cookie["domain"],
                            "path": cookie["path"],
                            "expires": cookie.get("expires", -1),
                            "httpOnly": cookie.get("httpOnly", False),
                            "secure": cookie.get("secure", False),
                            "sameSite": cookie.get("sameSite", "Lax")
                        }
                        for cookie in cookies
                    ],
                    "origins": []
                }
                
                # Пересоздаем request context с cookies
                request_context.dispose()
                request_context = p.request.new_context(
                    ignore_https_errors=True,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                        "Upgrade-Insecure-Requests": "1",
                        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"macOS"'
                    },
                    storage_state=storage_state
                )
                print(f"  ✅ Добавлено {len(cookies)} cookies в APIRequestContext")
        else:
            page = context.new_page()
            authenticate(context, page, root_url)
        
        # Настройки тайм-аутов
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(30000)
        
        try:
            # Получаем актуальный URL после авторизации
            current_url = page.url
            if current_url != root_url:
                print(f"🔄 URL изменился после авторизации: {current_url}")
                root_url = current_url
            
            crawler = WikiCrawler(page, output_dir, root_url, request_context)
            crawler.crawl()
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            raise
        finally:
            if request_context:
                request_context.dispose()
            browser.close()
            print("🔚 Браузер закрыт")


if __name__ == '__main__':
    main()
