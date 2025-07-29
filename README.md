# Yandex Wiki Backup

This project provides a containerized Python utility to archive authenticated, JavaScript-heavy wikis (such as Yandex Wiki) into a static HTML snapshot. The resulting files include all pages and assets for true offline browsing.

## Features

- Login using username/password, session cookies, or manual login.
- Crawls the wiki starting from a root URL and saves each page as HTML.
- Downloads images, stylesheets, and scripts referenced on each page.
- Rewrites links so the output is a self-contained static site.
- Runs inside Docker with Playwright for reliable rendering of dynamic pages.

## Getting Started

1. Copy the environment template and fill in your details:

```bash
cp .env.template .env
# Edit .env with your wiki URL and authentication info
```

2. Build and run using Docker Compose:

```bash
docker compose up
```

The downloaded site will be placed in the `output/` directory.

## Authentication Options

Yandex Wiki typically uses SSO. You have several ways to authenticate:

1. **Session Cookies** – In your browser's developer tools, copy the `Cookie` header while logged in and paste it into the `COOKIE_STRING` variable in `.env`. This avoids storing your password.
2. **Username/Password** – Provide `LOGIN_URL`, `USERNAME`, and `PASSWORD` in `.env` for automatic form-based login.
3. **Manual Login** – Set `HEADLESS=false` and run the container. A browser window will open; log in manually, then return to the terminal and press Enter.

Credentials must never be committed to source control. Only `.env.template` is tracked.

## Output

Pages and assets are stored under `output/` in a structure mirroring the original site. Open `index.html` inside the appropriate host folder to browse offline.

## Development

The main crawler lives in `src/backup.py` with helper functions in `src/utils.py`. Dependencies are listed in `requirements.txt` and installed in the provided Docker image.

---

This project is released under the MIT License.
