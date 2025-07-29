# Yandex Wiki Backup

This project provides a simple, containerised tool to archive an authenticated Yandex Wiki (or any JavaScript heavy wiki) into a static HTML site. All pages, images and other assets are downloaded so the result can be browsed offline.

## ✨ Recent Improvements

- **Fixed crawling logic**: Now properly crawls multiple pages instead of just the first one
- **Improved CSS handling**: Processes CSS files and updates resource URLs (fonts, images) for offline use
- **Enhanced SSL support**: Better handling of SSL certificate errors with multiple fallback options
- **Smart URL filtering**: Ignores analytics, API endpoints, and other non-content URLs
- **JavaScript path fixing**: Updates JavaScript public path variables for offline use
- **Better error handling**: Improved retry logic and error reporting
- **Resource deduplication**: Prevents downloading the same assets multiple times

## Features

- Uses [Playwright](https://playwright.dev/) for modern web automation.
- Supports authentication via Yandex credentials or existing browser cookies.
- Recursively crawls the wiki and rewrites links for offline use.
- Processes CSS files to update font and image references.
- Smart filtering of URLs to avoid crawling analytics and API endpoints.
- Output is a self-contained static site stored in `output/`.

## Getting Started

1. Copy `env.template` to `.env` and fill in the required values:
   ```bash
   cp env.template .env
   # Edit .env with your settings
   ```

2. Run `docker compose up` to start the crawl. The generated site will appear in the `output/` directory.
   A `viewer` service exposes the static files at <http://localhost:8080> with directory listing enabled.

### Environment Variables

- `WIKI_URL` – Root URL of your wiki (e.g. `https://wiki.yandex-team.ru`).
- `AUTH_METHOD` – `cookie` or `credentials`. Determines how authentication is performed.
- `COOKIE` – Cookie string exported from your browser. Used when `AUTH_METHOD=cookie`.
- `USERNAME` / `PASSWORD` – Credentials for Yandex Passport. Used when `AUTH_METHOD=credentials`.
- `OUTPUT_DIR` – Directory where the static site will be written (default: `output`).
- `IGNORE_SSL_ERRORS` – Set to `true` to allow crawling sites with self-signed certificates.

### Obtaining Cookies

1. Open your wiki in a browser where you are already logged in.
2. Open Developer Tools → Network → choose any request and copy the `Cookie` header.
3. Paste that value into the `COOKIE` variable in your `.env` file.

Using cookies avoids storing your username and password inside the container.

## Authentication Notes

The tool performs a login with Playwright in headless mode. When using `AUTH_METHOD=credentials` it will submit the Yandex Passport login form automatically. For single sign-on (SSO) flows or when automation is blocked, provide a valid `COOKIE` string instead.

## Output

The crawler writes all pages and assets relative to `OUTPUT_DIR`. Open `index.html` in that folder to browse your wiki offline.
You can also point your browser to `http://localhost:8080` while the compose stack is running to view the site via the built-in `viewer` service. Directory listing is enabled for easier navigation.

## How It Works

### Crawling Strategy

1. **Page Discovery**: Starts from the root URL and discovers wiki pages through internal links
2. **Smart Filtering**: Filters out analytics URLs, API endpoints, and non-content resources
3. **Asset Processing**: Downloads and processes CSS, JavaScript, images, and fonts
4. **CSS Resource Rewriting**: Updates URL references inside CSS files to point to local assets
5. **Path Normalization**: Converts absolute URLs to relative paths for offline browsing
6. **Deduplication**: Avoids re-downloading the same resources multiple times

### Supported Domains

The crawler automatically recognizes these Yandex-related domains as internal:
- Your wiki domain (e.g., `wiki.yandex-team.ru`)
- `yastatic.net` (CDN resources)
- `avatars.mds.yandex.net` (avatar images)
- `forms.yandex.ru` (embedded forms)
- `mc.yandex.ru` (analytics - downloaded but filtered from crawling)
- `yandex.ru` (main domain resources)

## Running natively

Docker is recommended, but you can also run the script locally:

```bash
pip install -r requirements.txt
playwright install --with-deps
python -m src.backup
```

## Troubleshooting

### SSL Certificate Errors
- Set `IGNORE_SSL_ERRORS=true` in your `.env` file
- The tool now uses multiple SSL bypass methods

### Limited Pages Crawled
- Check that your authentication is working correctly
- Verify that the wiki pages have proper internal links
- The crawler now has better link detection logic

### Missing Resources
- CSS resources and fonts are now properly processed and downloaded
- Check the console output for any download errors

### Large Wiki Sites
- The crawler has a default limit of 1000 pages to prevent infinite crawling
- Adjust the `max_pages` limit in `src/backup.py` if needed

## Security

**Never commit your real credentials.** The `env.template` file is provided so you can create your own `.env` with private information.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
