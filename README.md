# telemt-tg-bot

![Docker Image](https://github.com/illmouse/telemt-tg-bot/actions/workflows/docker.yml/badge.svg)

Telegram bot for managing users on a [telemt](https://github.com/telemt/telemt) MTProxy server via its control API.

## Features

- Create users with configurable `max_unique_ips` (prevents sharing proxy credentials)
- List users as a text overview with active IP / max IP info and status icons
- Filter user list by state: All / Active / Disabled
- Paginated list (30 users per page)
- Search users by name fragment
- View full user details (connections, active IPs, traffic, quota, expiry)
- Enable / disable users (via `max_tcp_conns`)
- Edit `max_unique_ips` on existing users
- Get a ready-to-forward proxy link message with connect buttons
- Delete users with confirmation
- Optional HTTP/SOCKS5 proxy for Telegram API connectivity
- Access restricted to configured Telegram usernames

## Requirements

- Running telemt instance with API enabled (`server.api.enabled = true`)
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Docker + Docker Compose

## telemt configuration

Enable the API in `telemt.toml`:

```toml
[server.api]
enabled = true
listen = "0.0.0.0:9091"
auth_header = "your-secret-value"
```

To fix link generation (telemt may generate links with internal IPs), set the public host:

```toml
[general.links]
public_host = "your.public.ip.or.hostname"
```

## Bot configuration

Copy `.env.example` to `.env` and fill in the values:

```
TELEMT_URL=http://192.168.1.1:9091      # telemt API address
TELEMT_AUTH=your-secret-value           # matches server.api.auth_header; leave empty to disable
BOT_TOKEN=123456:ABC-your-bot-token
ALLOWED_USERNAMES=alice,bob             # comma-separated Telegram usernames; leave empty to allow all
LINK_HOST=1.2.3.4                       # public IP/hostname to rewrite into proxy links; leave empty to use API-provided links as-is
PROXY_URL=socks5://user:pass@host:port  # optional proxy for Telegram API connections; leave empty to connect directly
```

## Running

The image is built automatically on every push to `main` and published to GHCR.

```bash
cp .env.example .env
$EDITOR .env
docker compose up -d
```

To update to the latest image:

```bash
docker compose pull && docker compose up -d
```

To build locally instead of pulling:

```bash
# uncomment `build: .` and comment out `image:` in docker-compose.yml
docker compose up -d --build
```

## Commands

| Action | How |
|---|---|
| Create user | ➕ Create User button or `/create` |
| List users | 👥 List Users button |
| Filter list | All / 🟢 Active / 🔴 Disabled buttons in the list |
| Search users | 🔍 Search button or `/search` |
| View user info | tap user in search results |
| Get proxy link | 🔗 Get Link from user info |
| Edit max IPs | ✏️ Max IPs from user info |
| Enable / disable | 🟢 Enable / 🔴 Disable from user info |
| Delete user | 🗑 Delete from user info |
| Cancel input | ✖ Cancel button or `/cancel` |
