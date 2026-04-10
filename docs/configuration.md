# Configuration

## Environment Variables

Copy `.env.example` to `.env`. All variables are read at startup.

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEMT_URL` | Yes | Base URL of telemt API, e.g. `http://192.168.1.1:9091` |
| `TELEMT_AUTH` | No | Value for `Authorization` header; leave empty to disable auth |
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `ALLOWED_USERNAMES` | No | Comma-separated Telegram usernames; empty = allow all |
| `LINK_HOST` | No | Public IP/hostname to rewrite into proxy links |
| `PROXY_URL` | No | HTTP or SOCKS5 proxy for Telegram API connections |
| `LOG_LEVEL` | No | Logging verbosity (DEBUG, INFO, WARNING, ERROR); default `INFO` |

## Proxy URL formats

```
http://host:port
http://user:pass@host:port
socks5://host:port
socks5://user:pass@host:port
```

## telemt Server Requirements

`telemt.toml` must have:

```toml
[server.api]
enabled = true
listen = "0.0.0.0:9091"
auth_header = "your-secret-value"   # matches TELEMT_AUTH

[general.links]
public_host = "your.public.ip"      # optional, fixes internal-IP links
```
