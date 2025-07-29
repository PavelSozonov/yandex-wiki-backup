# Yandex Wiki Backup

This project provides a simple, containerised tool to archive an authenticated Yandex Wiki (or any JavaScript heavy wiki) into a static HTML site. All pages, images and other assets are downloaded so the result can be browsed offline.

## Features

- Uses [Playwright](https://playwright.dev/) for modern web automation.
- Supports authentication via Yandex credentials or existing browser cookies.
- Recursively crawls the wiki and rewrites links for offline use.
- Output is a self-contained static site stored in `output/`.

## Getting Started

1. Copy `.env.template` to `.env` and fill in the required values.
2. Run `docker compose up` to start the crawl. The generated site will appear in the `output/` directory.
   An additional `viewer` service exposes the static files at <http://localhost:8080>.

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
You can also point your browser to `http://localhost:8080` while the compose stack is running to view the site via the built-in `viewer` service.

## Running natively

Docker is recommended, but you can also run the script locally:

```bash
pip install -r requirements.txt
playwright install --with-deps
python -m src.backup
```

## Security

**Never commit your real credentials.** The `.env.template` file is provided so you can create your own `.env` with private information.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
