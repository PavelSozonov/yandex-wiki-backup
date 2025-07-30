from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse, unquote


def ensure_dir(path: Path) -> None:
    """Создает директорию если она не существует"""
    path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от недопустимых символов"""
    # Удаляем или заменяем недопустимые символы
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Удаляем управляющие символы
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    # Ограничиваем длину
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_len = 255 - len(ext) - 1 if ext else 255
        filename = name[:max_name_len] + ('.' + ext if ext else '')
    return filename


def url_to_local_path(url: str, output_dir: Path, is_page: bool = False) -> Path:
    """Конвертирует URL в локальный путь"""
    parsed = urlparse(url)
    
    # Удаляем query parameters и fragments для файловых путей
    path = unquote(parsed.path)
    
    # Обрабатываем домен
    domain = parsed.netloc
    if domain:
        # Создаем структуру папок по доменам
        domain_parts = domain.split('.')
        domain_path = '/'.join(reversed(domain_parts)) if len(domain_parts) > 1 else domain
    else:
        domain_path = 'local'
    
    if is_page:
        # Для страниц создаем структуру директорий с index.html
        if path.endswith('/'):
            path += 'index.html'
        elif not path.endswith('.html'):
            # Создаем директорию с index.html внутри
            path = path.rstrip('/') + '/index.html'
    
    # Строим полный путь
    if path.startswith('/'):
        path = path[1:]  # убираем ведущий слеш
    
    # Очищаем компоненты пути
    path_parts = [sanitize_filename(part) for part in path.split('/') if part]
    
    # Создаем финальный путь
    if domain:
        local_path = output_dir / domain / Path(*path_parts) if path_parts else output_dir / domain / 'index.html'
    else:
        local_path = output_dir / Path(*path_parts) if path_parts else output_dir / 'index.html'
    
    return local_path


def hashed_filename(url: str, output_dir: Path) -> Path:
    """Создает хешированное имя файла для ассетов"""
    parsed = urlparse(url)
    
    # Получаем расширение из пути
    path = parsed.path
    ext = Path(path).suffix if path else ''
    filename = Path(path).name if path else ''
    
    # Для CSS и JS файлов от yastatic - сохраняем оригинальные имена
    # чтобы webpack мог найти динамические чанки
    if (ext in ['.css', '.js'] and 
        'yastatic.net/s3/cloud' in url and 
        ('static/freeze' in url or '/freeze/' in url) and
        filename):
        return output_dir / filename
    
    # Если нет расширения, пытаемся определить по Content-Type или URL
    if not ext:
        if 'css' in url.lower():
            ext = '.css'
        elif 'js' in url.lower():
            ext = '.js'
        elif any(img_ext in url.lower() for img_ext in ['png', 'jpg', 'jpeg', 'gif', 'svg']):
            # Попробуем извлечь расширение из URL
            for img_ext in ['png', 'jpg', 'jpeg', 'gif', 'svg']:
                if img_ext in url.lower():
                    ext = '.' + img_ext
                    break
            else:
                ext = '.bin'
        elif 'font' in url.lower() or any(font_ext in url.lower() for font_ext in ['woff', 'woff2', 'ttf']):
            for font_ext in ['woff2', 'woff', 'ttf']:
                if font_ext in url.lower():
                    ext = '.' + font_ext
                    break
            else:
                ext = '.font'
        else:
            ext = '.bin'
    
    # Создаем хеш от полного URL для остальных файлов
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    filename = f"{digest}{ext}"
    
    return output_dir / filename


def normalize_url(url: str) -> str:
    """Нормализует URL для консистентного обхода"""
    parsed = urlparse(url)
    
    # Удаляем fragment (все после #)
    normalized = parsed._replace(fragment='').geturl()
    
    # Удаляем дублирующиеся слеши
    normalized = re.sub(r'([^:])//+', r'\1/', normalized)
    
    return normalized


def is_asset_url(url: str) -> bool:
    """Проверяет, является ли URL ассетом"""
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    asset_extensions = [
        '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
        '.woff', '.woff2', '.ttf', '.eot', '.json', '.xml', '.txt'
    ]
    
    return any(path.endswith(ext) for ext in asset_extensions)
