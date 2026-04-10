# Architecture

## Overview

Single-process Python Telegram bot that wraps the telemt MTProxy control API.

## File Structure

| File | Role |
|------|------|
| `src/bot.py` | All bot handlers, conversation states, keyboard layouts, access control |
| `src/telemt_api.py` | Thin HTTP client for telemt REST API (`/v1/users`) |
| `docker-compose.yml` | Single-service deployment, pulls from GHCR |
| `Dockerfile` | `python:3.12-slim`, copies `src/`, runs `bot.py` |

## Key Constants (bot.py)

| Name | Value | Purpose |
|------|-------|---------|
| `PAGE_SIZE` | 10 | Users per page in list |
| `ENABLED_TCP_CONNS` | 65535 | Value written to re-enable a user |
| `USERNAME_RE` | `^[A-Za-z0-9_.\-]{1,64}$` | Validation for new usernames |

## Conversation States

| State | Constant |
|-------|----------|
| Waiting for username input | `WAITING_FOR_USERNAME = 1` |
| Waiting for max IPs on create | `WAITING_FOR_MAX_IPS = 2` |
| Waiting for max IPs on patch | `WAITING_FOR_PATCH_IPS = 3` |
| Waiting for search query | `WAITING_FOR_SEARCH = 4` |

## API Client (`telemt_api.py`)

Wraps `requests.Session`. Auth via `Authorization` header (raw value, not Bearer).
Methods: `get_users`, `get_user`, `create_user`, `patch_user`, `delete_user`.
Raises `RuntimeError` with telemt error message on non-2xx responses.

## Dependencies

- `python-telegram-bot[socks]==21.10` — bot framework + SOCKS5 proxy support
- `requests==2.32.3` — telemt API calls
