# Deploy

## Production (GHCR image)

Image is built and published automatically on every push to `main`.

```bash
cp .env.example .env
$EDITOR .env
docker compose up -d
```

Update to latest:

```bash
docker compose pull && docker compose up -d
```

## Local Build

In `docker-compose.yml`, uncomment `build: .` and comment out `image:`:

```bash
docker compose up -d --build
```

## CI/CD

GitHub Actions workflow at `.github/workflows/docker.yml` builds and pushes to `ghcr.io/illmouse/telemt-tg-bot:latest`.
