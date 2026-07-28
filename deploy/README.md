# Production deployment

This directory implements a release-directory deployment. It deliberately does **not** modify DNS, Cloudflare Tunnel configuration, account records or historical generated runs.

## Fixed production invariants

For the existing FEIAN deployment:

- service: `protocol-studio.service`;
- listener: `127.0.0.1:18771`;
- application root: `/srv/apps/protocol-studio`;
- release link: `/srv/apps/protocol-studio/current`;
- shared runs: `/srv/apps/protocol-studio/shared/runs`;
- shared account database: `/srv/apps/protocol-studio/shared/security.sqlite3`;
- environment file: `/etc/protocol-studio/protocol-studio.env`;
- public origin: `https://protocol.feian.online`;
- Cloudflare remains pointed at the same local listener.

Every release owns its own `.venv`. The mutable `shared/` directory is never copied into, or replaced by, a release.

## Release process

### 1. Build and verify away from production

```bash
python packaging/build_release.py --version 0.1.0
python packaging/verify_release.py dist/mcgs-full-chain-studio-0.1.0.tar.gz
```

Run all repository tests and complete the ownership/privacy review before uploading.

### 2. Back up the current state

Record the current target and service status. The deployment script performs an online SQLite backup immediately before switching. It does not delete prior releases.

### 3. Prepare the new release without switching traffic

Upload the archive together with this repository's `deploy/` and `packaging/` helpers to a protected operator directory, then run:

```bash
sudo bash deploy/deploy-release.sh \
  --archive /protected/incoming/mcgs-full-chain-studio-0.1.0.tar.gz \
  --release-id 20260728-0.1.0 \
  --expected-version 0.1.0 \
  --prepare-only
```

Preparation verifies the archive, safely extracts it, creates a per-release virtual environment, validates the production environment contract and performs an isolated health check on a temporary local port. It does not change `current` or restart production.

### 4. Switch only after the prepare gate passes

Run the same command with a new, not-yet-created release ID and explicit confirmation:

```bash
sudo bash deploy/deploy-release.sh \
  --archive /protected/incoming/mcgs-full-chain-studio-0.1.0.tar.gz \
  --release-id 20260728-0.1.0-prod \
  --expected-version 0.1.0 \
  --confirm-switch-production
```

The script:

1. verifies and extracts to an incoming directory;
2. builds that release's `.venv`;
3. validates the shared paths and authentication settings;
4. health-checks the new release on a temporary port;
5. backs up `security.sqlite3` using SQLite's online backup API;
6. atomically replaces only the `current` symlink;
7. restarts the existing systemd service;
8. checks the local and public health endpoints;
9. restores the previous symlink and service if a post-switch check fails.

It does not install or overwrite the systemd unit. `protocol-studio.service` in this directory is a reviewed reference for a fresh host; compare it with the active unit before any manual installation.

## Explicit rollback

```bash
sudo bash deploy/rollback-release.sh \
  --release-id <known-good-release-directory-name> \
  --confirm-rollback
```

Rollback changes only the `current` symlink and restarts the existing service. It never removes the failed release, shared runs, database or backups.

## Read-only health check

```bash
bash deploy/check-production.sh
```

A valid result requires both the local `/api/health` endpoint and the public endpoint to respond successfully. Listening sockets or `systemctl active` alone are insufficient.

## Environment file

Use `protocol-studio.env.example` only as a key/reference list. Never overwrite the existing production file during a deployment. Generate a password hash locally with `scripts/generate_password_hash.py`; do not put a real hash in source control.

## Human gates

Web and generator tests do not prove MCGS compilation, simulation or site correctness. Keep those as separate, recorded acceptance steps.
