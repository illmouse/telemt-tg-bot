# telemt-tg-bot

Telegram bot for managing users on a [telemt](https://github.com/telemt/telemt) MTProxy server via its control API.

## Quick Reference

- **Stack:** Python 3.12, python-telegram-bot 21.10, requests
- **Entry point:** `src/bot.py`
- **API client:** `src/telemt_api.py`
- **Deploy:** Docker Compose, image from GHCR (`ghcr.io/illmouse/telemt-tg-bot:latest`)
- **Config:** `.env` file (copy from `.env.example`)

## Project Index

| Area | Description | Doc |
|------|-------------|-----|
| Architecture | File structure, states, constants, API client | [docs/architecture.md](docs/architecture.md) |
| Configuration | All env vars, proxy formats, telemt config | [docs/configuration.md](docs/configuration.md) |
| Deploy | Docker Compose, local build, CI/CD | [docs/deploy.md](docs/deploy.md) |

## Accepted Decisions

- Access control via `ALLOWED_USERNAMES` env var (comma-separated), not a DB
- Users disabled by setting `max_tcp_conns=0`; re-enabled by setting it to `65535`
- Pagination at 10 users per page (`PAGE_SIZE = 10`)
- Auth to telemt API is a raw header value, not Bearer token
- Bot runs as a single process; no async worker or queue

## Workflow Rules

1. After changing env vars → update `docs/configuration.md` and `.env.example`
2. After adding/changing conversation states → update state table in `docs/architecture.md`
3. After changing deploy process → update `docs/deploy.md`

## Applied Learning

- `per_message=False` warning from PTB is suppressed intentionally; do not remove the filter
- Bot token is redacted from logs via `_RedactToken` filter on all root handlers
