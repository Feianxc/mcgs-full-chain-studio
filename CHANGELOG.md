# Changelog

All notable changes will be documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project intends to use [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.2] - 2026-07-29

### Fixed

- Make the deploy and rollback transaction guards capture the original exit status, ignore `INT`/`TERM`/`HUP`, and disarm `EXIT` before entering compensation. The top-level signal handler now ignores further signals and invokes the same guard explicitly with status `130`, so a signal delivered while an `EXIT` guard is active cannot escape without a fail-closed verdict. The compensation handlers retain their own signal mask as defense in depth. Explicit fallback and unexpected `EXIT` paths emit exactly one final safety verdict, persistently disable and stop the service, retain the active transaction marker, and terminate unsuccessfully.

### Verification boundary

- Thirty-six isolated dynamic Bash cases cover explicit fallback, unexpected status `1`, unexpected status `42`, five handler signal checkpoints, unexpected-false and unexpected-exit-42 signal handoff after guard entry, and eight compensation-failure modes for both deploy and rollback handlers. They assert message cardinality, terminal status, marker retention, and the disabled/inactive/dead/MainPID-zero state. Windows executes the actual signal-guard function for pre-mask handoff and trap-state probes after masking, but does not execute real POSIX signal delivery; real Linux/systemd staging, interruption, reboot, and production recovery acceptance remain separate gates.

## [0.1.1] - 2026-07-28

### Added

- Add a deterministic CycloneDX 1.5 JSON SBOM generator that binds the project name/version and six exact direct pins from `pyproject.toml` to a non-empty fully hashed production lock and an exactly matching wheel-only Wheelhouse, evaluates applicable `Requires-Dist` markers for OpenCloudOS/Linux x86_64 with CPython 3.11.6, and validates the resulting dependency closure. Independent readback covers 17 locked application components and 18 dependency records; official CycloneDX Schema validation, same-commit publication provenance and target runtime acceptance remain separate release gates. Deployment tools introduced by `venv`/`ensurepip` are outside this application-dependency SBOM.
- Add release identity to `/api/health`: when `release-manifest.json` is present, the JSON `release_manifest_sha256` field and the single `X-MCGS-Release-Manifest-SHA256` response header expose its lowercase SHA-256. A source/development tree without that file returns JSON `null` and omits the header. `check-production.sh` requires `PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256` by default; explicit `PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY=true` is mutually exclusive and only reports `release_identity=not_requested` for deliberate legacy checks.

### Changed

- Require an authenticated 64-character archive digest through `--archive-sha256`; the deployment script snapshots the archive and rejects digest or in-flight content drift.
- Require a root-owned, wheel-only offline directory through `PROTOCOL_STUDIO_WHEELHOUSE` and install the fully transitive production lock with hashes, without index or source distributions.
- Define `--prepare-only` as an ephemeral dry-run that removes its `.incoming-*` candidate. The same release ID can be reused for the formal switch, which independently rebuilds and revalidates the candidate.
- Move deployment control logs, backups, release records and the primary lock into root-only `.deploy-state`, while also honoring an existing legacy `.deploy.lock` compatibility lock.
- Require the release policy and manifest to cover exactly nine non-empty public trees, with one stable entry sentinel for every required tree; optional files elsewhere in a tree do not become mandatory merely because they appeared in one build.
- Use strict schema 3 active interrupted-transaction phases: `switching`/`rolling_back`, `deploy_committed_pending_activation`/`rollback_committed_pending_activation`, and `recovery_committed_pending_activation`. Ordinary deploy/rollback transitions atomically change only `status`; the precommit recovery transition additionally binds `recovery_activation_release_id` and `recovery_activation_runtime_mode`, after which those fields remain immutable. Newly published passed evidence is schema 5 and binds the final public origin/host, EnvironmentFile, unit/drop-in, ordered `exec_start_pre_argvs`, the external runtime baseline/helper/fingerprint, ordinary-restart integrity gate and publication configuration gate. Schema 2 through 4 passed records are audit-only: the v0.1.1 deploy, rollback and recovery paths recognize them only to reject activation before systemd or transaction-state mutation. They are not implicitly migrated and must not be confused with the independently registered legacy shared-runtime baseline, which remains supported for the first upgrade and explicit legacy rollback.
- Add an external ordinary-restart integrity gate under the deployment root: an immutable root-owned helper verifies the complete active Release and its exclusive, fsynced runtime baseline before the Release-local environment validator runs. External baseline schema 1 now requires the 64-character lowercase `runtime_guard_helper_sha256`; the actually executed helper is rehashed and must match it, so an older schema 1 baseline without that field cannot approve a modern restart. `check-production.sh` reports `installed_runtime_identity=passed|failed|not_requested` and only reports modern `release_identity=passed` when the installed runtime, local Manifest and public Manifest identities all pass. Existing helper bytes are never silently replaced; a helper change requires a separate audited migration.
- Reset inherited systemd `Environment=` values before setting only `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`, bind canary/guarded/final process environments through `/proc`, and set `StartLimitIntervalSec=60s` with `StartLimitBurst=3` so repeated integrity failures do not cause unbounded full-tree hashing. Linux/systemd staging remains the required runtime proof.
- Persistently disable and prove zero canonical-target enablement links before installing a volatile `/run` guard with `Restart=no` and `RuntimeMaxSec=300s`; scan every symlink in systemd `.wants` and `.requires` directories, so a differently named alias that resolves to the same unit is also rejected.
- Prepare protected pending deploy/rollback/recovery evidence before logical commit. After commit, remove the guard, restart and validate the promised target without the guard, enable only the unique standard `multi-user.target.wants` topology, and repeat full provenance/health checks. Reconcile or publish the passed record, persist the final record and pending-record unlink, and only then archive the active marker. Publication failure retains the marker so recovery can retry idempotently.
- Make recovery phase-aware: precommit deploy/rollback recovery returns to the recorded previous runtime, while committed recovery can only finalize the already-promised target.
- Require every modern release-local local/public health gate in deploy, rollback and recovery to match the recorded manifest digest exactly. Only the explicitly registered legacy baseline is availability-only because it predates the identity header; availability must not be reported as release identity or full provenance.
- Copy `pyproject.toml` into the Docker image and derive FastAPI application metadata from its project version, keeping the reported application version aligned with `0.1.1`.
- Split the tag workflow into isolated test, clean-package and attestation jobs. The package job uses a credential-free fresh checkout, builds the source archive before network dependency retrieval, downloads only hash-locked wheels, performs an offline exact-lock install plus `pip check`/import smoke outside the checkout, rechecks source and archive identity, and grants OIDC only to the final attestation job.
- Harden ordinary systemd restarts as well as transactions: clear the reviewed glibc/OpenSSL/Python/Bash/Uvicorn startup-control environment set through `UnsetEnvironment`, reject unknown dangerous prefixes, and run both validation and Uvicorn with isolated, no-bytecode, unbuffered `python -I -B -u` argv.

### Fixed

- Normalize the complete immutable release tree and per-release virtual environment for read/execute access by the unprivileged systemd account.
- Run import/process checks and a transient systemd canary against the exact candidate with an isolated account database and runs directory.
- Migrate the legacy shared virtual environment through one managed systemd drop-in without overwriting the reviewed base unit.
- Treat the current symlink, managed drop-in, effective systemd configuration and service health as one stopped-service switch transaction.
- Persist interrupted-transaction and pending-record evidence, freeze the registered legacy baseline, and fail closed for explicit phase-aware recovery instead of presenting an automatic restore as success.

### Security

- Upgrade FastAPI to 0.140.7 for Starlette 1.3.1 compatibility, and replace the advisory-affected Starlette and Jinja2 pins with Starlette 1.3.1 and Jinja2 3.1.6.
- Refresh the OpenCloudOS 9.4 / CPython 3.11 x86_64 production lock as a 17-package wheel-only set with exactly one SHA-256 per package. Promote the formal Wheelhouse input only after target-host digest readback, no-index hash-required installation, `pip check` and dependency-import smoke; the exact source archive's complete Linux runner remains a separate release gate.
- Close every inherited POSIX file descriptor above `2` in `run_with_env.py` before `exec`; rollback and recovery also close Shell descriptors `8` and `9` before launching their long-lived canaries as defense in depth. Windows tests do not stand in for the separate POSIX `/proc/self/fd` runtime check.
- Preserve the private service baseline `UMask=0077` through deploy, rollback and recovery records and checks.
- Reset `ReadWritePaths` before granting only `/srv/apps/protocol-studio/shared`, preventing systemd list-value accumulation across the base unit and drop-in.
- Require deployment Shell/Python helpers, the release verifier and allowlist to execute from a root-owned, non-group/other-writable control path rather than a user-writable checkout.
- Bind modern release provenance to the immutable source tree, release-local runtime, production lock, installed distributions, permissions and ownership.
- Read back persistent-disabled topology, `inactive/dead`, `MainPID=0`, original-process disappearance and marker retention on transaction failure. The `/run` guard is intentionally reboot-volatile; an unconfirmed fail-closed result requires `DO NOT REBOOT` and manual systemd recovery.
- Retain orphan releases for explicit manual quarantine only; deploy, rollback and recovery do not auto-delete or auto-promote them.
- Disable `.curlrc`, bypass proxies explicitly and clear common proxy/`CURL_HOME` variables for every deployment health request, so operator environment cannot silently weaken TLS or reroute local/public checks.
- Reject `PROTOCOL_STUDIO_RESOURCES_ROOT` in production, including empty or apparently in-release values, so protocol libraries and templates cannot be redirected outside the Manifest-covered release tree.
- Bound SQLite backup, integrity/schema verification and hashing to one monotonic total deadline, including lock waits and backup/query progress callbacks. A failure before the destination hardlink and parent-directory `fsync` publication commit removes the helper-owned destination; a later deadline or cleanup failure emits a fixed error while retaining the complete, inspectable committed backup.
- Reject non-canonical or symlinked shared runs/database identities, privileged loader/startup environment drift, Uvicorn CLI environment overrides, and non-canonical public origins. The public origin must be a lowercase HTTPS DNS origin without credentials, port, path, query or fragment; `check-production.sh` separately requires a DNS public endpoint and a loopback-only local endpoint.

### Verification boundary

- The Docker source contract now pins `python:3.11.6-slim-bookworm` to manifest-list digest `sha256:cc758519481092eb5a4a5ab0c1b303e288880d59afc601958d19e95b300bc86b`; the exact Docker context and base-image pin are covered by packaging tests.
- Static deployment contract/SBOM/Docker-context tests do not constitute a Docker image build/run, staging or production deployment, rollback, interrupted-transaction recovery or completed Release asset build. The local release workstation has no Docker CLI, and the current Docker context does not include the generated `release-manifest.json`; container release/production is therefore blocked. The transient canary covers only the isolated candidate and selected restrictions; target-host support for transient `EnvironmentFile`/`BindPaths`/`UnsetEnvironment` behavior, rollback/recovery `/proc/<pid>/environ`, production shared state, public authenticated workflows and fault-injection exercises remain separate acceptance gates.
- Runtime rollback is not database or request rollback. The online SQLite backup is evidence and a manual restore input; the scripts do not undo shared database, session or generated-run writes. Production requires a backward-compatible data contract, a rehearsed restore, an external traffic drain or explicit maintenance window, read-only confirmation that the configured administrator already exists, and real login/session/permission/generator acceptance before traffic is restored.

## [0.1.0] - 2026-07-28

### Added

- Unified project assembly and protocol-generation source layout.
- Shared authentication, session and CSRF security boundary.
- Public-data policy, privacy scan and deterministic allowlist packaging.
- Release-directory deployment model with shared state and atomic rollback.

### Security

- Production credentials, account databases and generated runs are excluded from source releases.

### Known issues

- `v0.1.0` is published as a prerelease with known production-safety defects. `v0.1.1` is retained for audit only because its explicit transaction-compensation path can emit contradictory final safety verdicts. Do not use either version to deploy, roll back or recover a host; use the reviewed `v0.1.2` contract instead.

[Unreleased]: https://github.com/Feianxc/mcgs-full-chain-studio/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/Feianxc/mcgs-full-chain-studio/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Feianxc/mcgs-full-chain-studio/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Feianxc/mcgs-full-chain-studio/releases/tag/v0.1.0
