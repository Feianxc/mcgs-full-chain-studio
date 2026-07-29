# Production deployment

This directory implements a release-directory deployment. It deliberately does **not** modify DNS, Cloudflare Tunnel configuration, account records or historical generated runs.

> **Release warning:** these instructions describe the `v0.1.2` contract. The public `v0.1.0` release is a prerelease with known production-safety defects. `v0.1.1` is retained for audit only because an explicit transaction-compensation path can emit contradictory final safety verdicts. Do **not** use `v0.1.0` or `v0.1.1` to deploy, roll back or recover any host.

> **Evidence boundary:** repository tests and `tests/deploy_contract_test.py` validate source, syntax and static text contracts. They do not execute a real systemd transaction. A release is not production-verified until the exact frozen archive, Wheelhouse and control bundle have passed prepare, switch, runtime, rollback/recovery and application acceptance on the target Linux host. This document does not assert that such production verification has already occurred.

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

The scripts do not overwrite the administrator-owned base unit. They manage only:

```text
/etc/systemd/system/protocol-studio.service.d/90-release-runtime.conf
```

The repository's `protocol-studio.service` is a reviewed reference for a fresh host, not an instruction to replace an existing production unit.

## Mandatory inputs and trust boundary

Every deployment requires all of the following:

1. the frozen `mcgs-full-chain-studio-0.1.2.tar.gz` archive;
2. its 64-character SHA-256 obtained from an authenticated release/CI channel and passed with `--archive-sha256`;
3. a complete offline, wheel-only directory selected through `PROTOCOL_STUDIO_WHEELHOUSE`;
4. the matching `requirements.production.lock.txt` inside the archive;
5. one version-matched root-only control bundle containing `deploy-release.sh`, `rollback-release.sh`, `recover-transaction.sh`, their Python helpers, and `packaging/verify_release.py` plus `packaging/release-allowlist.json`.

The control bundle, Wheelhouse, their files and every parent directory must be canonical non-symlink paths owned by `root:root` and not writable by group or other. Run the scripts from that frozen control bundle, **not** from a normal user-writable checkout. The scripts bind `/usr/bin/python3`, use isolated Python mode for control helpers, require Linux x86_64 CPython 3.11, and install only hash-locked wheels with `--no-index`, `--only-binary=:all:` and `--require-hashes`.

The protected Shell entry points use `#!/usr/bin/bash -p` and verify privileged Bash mode before doing any work. Execute them directly, as shown below, or explicitly with `/usr/bin/bash -p`. Do **not** invoke them as `bash script.sh` or `/usr/bin/bash script.sh`: that bypasses the shebang, omits `-p` and is intentionally rejected.

Production EnvironmentFiles must not contain `PROTOCOL_STUDIO_RESOURCES_ROOT`, even with an empty value or a path that appears to point back into the current release. The validator rejects the key so protocol libraries, address profiles and export templates can only come from the Manifest-covered `resources/protocol` inside the active release. The override remains a development-only feature outside this production validator.

The managed systemd runtime resets and replaces `ExecStartPre`, `ExecStart` and the inherited `Environment=` list. It then installs exactly two ordered pre-start gates for a modern runtime: first the root-owned external `/usr/bin/python3` runs the immutable runtime-fingerprint helper against `current` and its external baseline; only after that succeeds does the release-local `.venv` run `validate_production_env.py`. The service process and environment validator run with `python -I -B -u`. The only explicit fixed service variables are `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`; an exact `UnsetEnvironment=` list removes Bash, glibc/OpenSSL loader, Python and Uvicorn startup controls inherited from the manager or EnvironmentFile. Deploy, rollback, recovery and the read-only checker read the effective list values back and fail closed on ordering or environment drift. `UnsetEnvironment` is defense in depth, not permission to keep dangerous keys in the production EnvironmentFile.

The external integrity control lives below `/srv/apps/protocol-studio/runtime-guard/`: its directories must be canonical `root:root` mode `0755` paths without extended/default ACLs, while `runtime_fingerprint.py` and each released baseline must be regular non-symlink `root:root` mode `0444` files without extended ACLs. A baseline uses outer schema version 1, requires the lowercase SHA-256 of the exact external helper bytes in `runtime_guard_helper_sha256`, and embeds a complete runtime fingerprint using schema version 2. Both `--verify-current` and `--verify-release` hash the ordinary non-symlink helper file that is actually executing and require an exact match with that baseline field before approving the release. Missing historical fields, extra fields, duplicate keys, non-finite values, booleans masquerading as integers and non-canonical digests fail closed; an older baseline without the helper digest cannot approve a modern ordinary restart. The fingerprint binds the whole release source tree, release-local `.venv`, production lock, interpreter and installed distribution inventory; the external Manifest digest remains an independent expected input. Existing immutable helper bytes are never overwritten by an application release. If the candidate helper differs, deployment is deliberately blocked: helper replacement requires a separate audited migration with its own rollback and ordinary-restart validation.

Schema 5 passed evidence repeats the baseline SHA-256, canonical embedded-fingerprint SHA-256 and helper SHA-256. Deploy, rollback and recovery require those evidence values to agree with the current baseline, fingerprint and helper bytes; the verifier independently requires the baseline helper digest to agree with the executing helper. Consequently, changing only the external helper, including merely appending a comment, blocks ordinary restart and makes `check-production.sh` nonzero through its `--verify-current` gate. The integrity boundary assumes an accidental or isolated single-file modification. A malicious root actor that deliberately rewrites both the helper and its root-owned baseline consistently is outside this threat model and requires host-level measured boot, immutable infrastructure or an external trust anchor.

The managed unit also fixes `StartLimitIntervalSec=60s` and `StartLimitBurst=3`. This bounds repeated full-tree hashing after an automatic restart fails its integrity gate. After correcting a deliberate drift in staging, use `systemctl reset-failed` before the clean recovery restart. The limit must be proven not to interfere with the two controlled starts used by deploy, rollback or recovery; static Windows contracts do not establish that Linux/systemd behavior.

`PROTOCOL_STUDIO_PUBLIC_ORIGIN` must be an origin-only canonical lowercase HTTPS DNS value such as `https://protocol.feian.online`: no credentials, IP literal, port, path, query or fragment. The read-only checker accepts `PROTOCOL_STUDIO_LOCAL_ORIGIN` only as `http://127.0.0.1:<port>`, with a decimal port from `1` through `65535` and no path, query or fragment. Public and local origins must remain distinct.

The v0.1.2 direct production pins are FastAPI `0.140.7`, Starlette `1.3.1`, Uvicorn `0.38.0`, Pydantic `2.12.5`, Jinja2 `3.1.6` and openpyxl `3.1.2`. The production lock expands these to 17 packages. The formal 17-wheel input was promoted only after target-host digest readback, no-index hash-required installation, `pip check` and dependency-import smoke passed. The exact frozen source archive's complete Linux runner, staging transaction and production acceptance remain separate gates. The dependency SBOM covers those 17 locked application dependencies; it does not automatically inventory pip, setuptools or other deployment tooling introduced by `venv`/`ensurepip`.

The application reads its version from `pyproject.toml`, and FastAPI metadata therefore reports `0.1.2`. The `Dockerfile` copies `pyproject.toml` beside the production lock before copying application source and pins the official `python:3.11.6-slim-bookworm` manifest list to `sha256:cc758519481092eb5a4a5ab0c1b303e288880d59afc601958d19e95b300bc86b`. The digest and Docker context are source contracts only: the local release workstation has no Docker CLI, so no formal image build, runtime or acceptance is claimed here. The current Docker context does not copy the packaging-generated `release-manifest.json`; its health response therefore has no Release identity. That image is **not permitted for container production** until a Manifest-bound image contract, real build/run, vulnerability review and runtime acceptance have passed.

On POSIX, `run_with_env.py` closes every inherited file descriptor above `2` before `exec`, preserving only stdin/stdout/stderr. Rollback and recovery also close their Shell descriptors `8` and `9` before launching long-lived canaries. This defense-in-depth contract still requires a real Linux `/proc/self/fd` and lock-release check; Windows static or unit-test evidence is not a substitute.

A typical protected layout is:

```text
/root/protocol-studio-v0.1.2-control/
  deploy/                       frozen Shell/Python control helpers
  packaging/                    frozen verifier and release allowlist
  incoming/
    mcgs-full-chain-studio-0.1.2.tar.gz
    mcgs-full-chain-studio-0.1.2.tar.gz.sha256
  wheelhouse/                   root-owned .whl files only
```

Keep the archive digest as an operator-controlled value from the authenticated sidecar. Checking the sidecar on the host is necessary, but recomputing a digest from an unauthenticated archive is not an authenticity check.

## Persistent deployment control state

`v0.1.2` keeps deployment control data outside both releases and shared application data:

```text
/srv/apps/protocol-studio/.deploy-state/
  deploy.lock                   root-only current lock
  logs/                         canary and operation logs
  backups/                      SQLite/unit/drop-in evidence
  deployments/                  release records and archived transaction markers
```

Every deploy, rollback and recovery operation takes `.deploy-state/deploy.lock`. If the historical `/srv/apps/protocol-studio/.deploy.lock` exists, it is also taken as a compatibility lock; this dual-lock protocol prevents overlap with an older deployment tool. Do not delete either lock to bypass an active operation.

SQLite backup, inspection and integrity verification share one monotonic total deadline (300 seconds by default, bounded to 0.05–900 seconds through the helper CLI). Busy waits, backup progress, integrity/schema queries and file hashing consume the same budget. Before the destination hardlink and parent-directory `fsync` publication commit, a deadline failure removes the helper-owned destination. After that commit, a later `deadline_exceeded` or `post_publish_cleanup_failed` result retains the complete destination for independent `inspect` verification. This bounds helper-controlled SQLite work; individual synchronous filesystem syscalls still require real staging fault tests.

The SQLite copy is protected evidence and a manual recovery input. Deploy, rollback and recovery do **not** automatically replace the live database with that copy. A runtime rollback changes source/runtime configuration only; it does not undo account, session or generated-run writes made during the switch window. Production therefore requires backward-compatible data schema, a rehearsed database restoration procedure, and either external traffic isolation or an explicit maintenance window. Restore traffic only after recovery and public application acceptance are complete.

The active marker is `/srv/apps/protocol-studio/.deploy-transaction.json`. It uses schema version 3 and records the exact previous target, effective executable/argv, working directory, service identity, environment file, public origin/host, `ReadWritePaths`, `UMask=0077`, database backup, base-unit/drop-in evidence and enablement baseline. Its operation-specific top-level key set is strict: extra, missing or duplicate JSON fields are rejected. Ordinary deploy/rollback transitions atomically replace the marker while changing only `status`. A precommit recovery transition into `recovery_committed_pending_activation` additionally binds `recovery_activation_release_id` and `recovery_activation_runtime_mode`; subsequent transitions preserve those fields unchanged.

New deploy, rollback and recovery passed evidence uses schema version 5. It binds the public origin/host, EnvironmentFile, administrator base unit, managed drop-in, the ordered `exec_start_pre_argvs` array, ordinary-restart integrity-gate result, fixed external runtime-baseline path and SHA-256, embedded fingerprint SHA-256, immutable helper SHA-256 and final publication configuration gates. Schema 2 through 4 deployment records are recognized only so an administrator can identify historical evidence; they are **audit-only and are not activation-compatible** with these scripts. They cannot be the current release-local runtime at deploy/rollback entry, an explicit rollback target, or a recovery previous/committed target. In particular, schema 4's historical single `exec_start_pre_argv` cannot be upgraded implicitly into schema 5's ordered dual gate without changing its recorded systemd provenance. An older release requires a separate reviewed migration that publishes new provenance; these scripts never synthesize an external baseline or rewrite historical evidence while activating it. The independently registered no-`.venv` legacy shared-runtime baseline is a different contract and must not be confused with schema 2 deployment evidence.

Accepted phases are intentionally narrow:

| Operation shape | Precommit status | Logically committed status |
| --- | --- | --- |
| deploy | `switching` | `deploy_committed_pending_activation` |
| rollback | `rolling_back` | `rollback_committed_pending_activation` |
| recovery of a precommit operation | original precommit status | `recovery_committed_pending_activation` |

`switching` and `rolling_back` promise restoration of the recorded previous runtime if recovery is needed. Once a deploy or rollback marker reaches its `*_committed_pending_activation` phase, the target is the only permissible recovery target: recovery must finish that target rather than silently return to the previous release. `recovery_committed_pending_activation` means the recovery-selected previous target has itself been logically committed and must be finalized.

The marker remains active through guarded validation, logical commit, guard removal, an unguarded restart, enablement and post-enable provenance/health validation. The script then publishes or reconciles the passed record, persists the final record and deployment directory, removes the protected pending name, and persists that unlink. Only after those steps succeed is the active marker archived under `.deploy-state/deployments/`. Publication failure keeps the active marker and protected evidence so recovery can re-enter the exact state.

### Failed/orphan evidence is not an automatic cleanup target

The scripts do not delete prior releases, published runtime baselines, failed releases, locks, backups or transaction archives. A release directory that exists without an active marker or corresponding passed deployment record can be evidence of the narrow interruption window between candidate promotion and marker publication. Treat it as an **orphan/failed candidate**, not as deployed or reusable: the same release ID will be refused. If the corresponding published baseline exists, quarantine the release and baseline together after canonical-path, active-target, ownership, ACL and hash review. A leftover `.pending-<release-id>.json` baseline is a separate protected failure artifact and must also be reviewed and quarantined explicitly. Deploy, rollback and recovery never delete a published baseline or auto-promote/quarantine these artifacts. Before promotion, the deploy exit path removes only a safely typed, helper-owned pending baseline and temporary transaction marker; it refuses cleanup if their type, owner or mode is unexpected.

Hidden `.pending-deploy-*`, `.pending-rollback-*` and `.pending-recovery-*` records are protected commit evidence, not temporary clutter. They are fsynced before the related logical status transition. With an active committed marker, recovery validates and reconciles pending-only, matching pending+final, or trusted final-only evidence; it fsyncs the final state, removes only the matching pending name, persists the directory and refuses mismatched evidence. A v0.1.2 archived marker without its trusted final passed record violates the completion contract and must not be called passed or repaired by hand.

The historical `.deploy.lock` is a compatibility lock file, not a success marker. Its mere presence is not an error when no process holds its `flock`, and the v0.1.2 scripts intentionally preserve it. Never delete it to work around lock contention; identify the holder and reconcile the older operation first.

## Release process

### 1. Build and verify away from production

```bash
python packaging/build_release.py --version 0.1.2
python packaging/verify_release.py dist/mcgs-full-chain-studio-0.1.2.tar.gz
(cd dist && sha256sum --check mcgs-full-chain-studio-0.1.2.tar.gz.sha256)

RELEASE_COMMIT='replace-with-reviewed-release-commit'
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct "$RELEASE_COMMIT")"
python packaging/generate_sbom.py \
  --lock requirements.production.lock.txt \
  --wheelhouse dist/wheelhouse-v0.1.2 \
  --output dist/mcgs-full-chain-studio-0.1.2.cdx.json \
  --application-name mcgs-full-chain-studio \
  --application-version 0.1.2
(cd dist && sha256sum --check mcgs-full-chain-studio-0.1.2.cdx.json.sha256)
```

Build the wheel-only Wheelhouse from the reviewed production lock for the intended Linux x86_64/CPython 3.11 ABI. The implemented v0.1.2 SBOM contract binds the project name/version and six exact direct pins declared by `pyproject.toml` to a non-empty fully hashed lock and an exactly matching pure-wheel Wheelhouse, evaluates applicable `Requires-Dist` markers for OpenCloudOS/Linux x86_64 with CPython 3.11.6, and validates the dependency closure before writing CycloneDX 1.5 JSON plus a checksum sidecar. Independent readback covers 17 locked application components and 18 dependency records, and the formal Wheelhouse input has passed target-host offline dependency acceptance. Official CycloneDX Schema validation, same-commit GitHub publication provenance, the exact source archive's complete Linux runner and runtime deployment acceptance remain separate gates.

The source release verifier independently requires the allowlist policy and Manifest to cover exactly nine non-empty release trees and the stable entry sentinel assigned to each tree. Other optional files within those trees remain optional.

When a formal release tree contains `release-manifest.json`, `/api/health` exposes its lowercase SHA-256 both as JSON `release_manifest_sha256` and as the single `X-MCGS-Release-Manifest-SHA256` header. A source/development tree without the Manifest returns JSON `null` and omits the header; that mode proves availability only, not release identity.

The formal `v0.1.2` GitHub Release asset **plan** is:

```text
mcgs-full-chain-studio-0.1.2.tar.gz
mcgs-full-chain-studio-0.1.2.tar.gz.sha256
mcgs-full-chain-studio-0.1.2.cdx.json
mcgs-full-chain-studio-0.1.2.cdx.json.sha256
```

Run all repository tests and complete the ownership/privacy review before uploading. Rebuild and independently read back all four assets from one frozen commit, then preserve the authenticated archive digest separately for `--archive-sha256`. The list above is a plan, not evidence that the assets or GitHub Release already exist. The offline Wheelhouse remains a separate authenticated deployment input unless a future release process defines and verifies a dedicated Wheelhouse bundle.

### 2. Install the frozen root-only inputs

Copy the archive, checksum sidecar, Wheelhouse and matching control bundle into the protected layout described above. Set `root:root` ownership, remove group/other write access from every file and parent directory, and verify that the Wheelhouse contains regular `.whl` files only.

The examples below use one release ID for both prepare and switch:

```bash
CONTROL=/root/protocol-studio-v0.1.2-control
ARCHIVE="$CONTROL/incoming/mcgs-full-chain-studio-0.1.2.tar.gz"
ARCHIVE_SHA256='<64-lowercase-hex-from-authenticated-sidecar>'
WHEELHOUSE="$CONTROL/wheelhouse"
RELEASE_ID='20260729-0.1.2-prod'
```

### 3. Prepare the new release without switching traffic

Run the frozen control script with both mandatory supply-chain inputs:

```bash
sudo /usr/bin/env PROTOCOL_STUDIO_WHEELHOUSE="$WHEELHOUSE" \
  "$CONTROL/deploy/deploy-release.sh" \
  --archive "$ARCHIVE" \
  --archive-sha256 "$ARCHIVE_SHA256" \
  --release-id "$RELEASE_ID" \
  --expected-version 0.1.2 \
  --prepare-only
```

`--prepare-only` is an **ephemeral dry-run**. It verifies and safely extracts the archive, creates the candidate `.venv` from the offline Wheelhouse, validates the production environment contract, normalizes and fingerprints the immutable tree, and runs the candidate canaries. On success it deletes the `.incoming-*` candidate and retains no release directory. It does not change `current`, install the managed production drop-in, stop/restart the production service, or modify the production account database and generated runs. It reads the account database only to create an online isolated copy for the canary. The root-only `.deploy-state` lock and preflight logs/evidence remain for audit; "ephemeral" describes the candidate, not the control evidence.

Because the incoming candidate is removed, the **same release ID may be reused** for the formal switch. The switch command independently rebuilds and revalidates the candidate from the same archive, authenticated digest and Wheelhouse; prepare-only does not persist an approval token or reusable `.venv`.

#### What the transient systemd canary proves

The pre-switch canary starts the exact extracted candidate and its candidate `.venv` as the real unprivileged service identity in a uniquely named transient systemd unit. It loads the production `EnvironmentFile`, bind-mounts an isolated preflight `shared/` tree over the normal shared path, uses a temporary local port, and applies the selected production-equivalent working-directory, `UMask=0077` and sandbox/hardening properties. It reads back effective properties, PID argv/cwd and private-vs-live inode identity, checks local `/api/health` plus the unauthenticated `/` redirect to `/login`, then stops/reset-failed, proves the PID is gone and deletes the private preflight root.

When it passes on the target host, this proves that systemd can start that candidate under those selected restrictions without writing production mutable state. The source implementation and static tests alone do **not** prove that the FEIAN systemd version accepts/translates transient `EnvironmentFile`, `BindPaths` and property readback exactly as expected. The canary also does not prove the administrator base unit plus installed managed drop-in, the `current` symlink transaction, public ingress, authenticated sessions, real generators, boot enablement, automatic rollback or interrupted-transaction recovery. Those require the formal transaction and separate acceptance exercises.

Windows contracts cover environment parsing and selected command-line/property text, but they cannot prove any actual Linux process environment. Linux staging must independently read `/proc/<pid>/environ` for deploy, rollback and recovery canaries, guarded processes and final processes. Every key/value from the strictly parsed EnvironmentFile plus the two fixed Python variables must match exactly, while rejected loader, Python, Bash and Uvicorn startup controls must be absent. Runs and security-database paths must remain bound to the intended deployment root.

### 4. Switch only after the prepare gate passes

Record the current target, PID, effective unit configuration and service status. Then rerun the same frozen inputs with the same release ID and explicit confirmation:

```bash
sudo /usr/bin/env PROTOCOL_STUDIO_WHEELHOUSE="$WHEELHOUSE" \
  "$CONTROL/deploy/deploy-release.sh" \
  --archive "$ARCHIVE" \
  --archive-sha256 "$ARCHIVE_SHA256" \
  --release-id "$RELEASE_ID" \
  --expected-version 0.1.2 \
  --confirm-switch-production
```

The script:

For modern release-local runtimes, every transaction health gate that reaches local and public `/api/health` requires exactly one well-formed identity header matching the recorded Manifest SHA-256. Deploy, rollback and recovery apply this rule throughout their modern-runtime phases. The one registered legacy baseline predates the header and is deliberately availability-only; its successful health response is neither release identity nor complete provenance evidence.

Before any marker publication or systemd mutation, the existing runtime must be either the separately registered legacy shared-runtime baseline or a strict schema 5 release-local record whose exact dual-gate drop-in, fixed baseline path, Manifest, runtime fingerprint and helper hashes all verify. A schema 2-4 release-local current is rejected at this read-only boundary, including a schema 4 current with its historical single pre-start gate.

1. verifies and extracts to an incoming directory;
2. builds that release's `.venv`;
3. validates the shared paths and authentication settings;
4. runs isolated process and transient systemd canaries on the same candidate;
5. backs up `security.sqlite3` using SQLite's online backup API;
6. prepares the schema 3 `switching` marker temporary payload, exclusively creates and fsyncs a mode-`0444` pending external runtime baseline, fsyncs the marker temporary file, promotes and persists the immutable candidate, then exclusively hardlinks the final baseline, verifies the pending/final inode, fsyncs the file and directory, removes the pending name and fsyncs the directory again;
7. only after the final baseline is durable, atomically publishes and fsyncs the active marker, then re-verifies the promoted release against that baseline before touching systemd; a failure here retains the marker and leaves systemd untouched;
8. **persistently disables** the service and proves that no enablement symlink remains;
9. installs `/run/systemd/system/protocol-studio.service.d/99-transaction-runtime-guard.conf` with `Restart=no` and `RuntimeMaxSec=300s`, then **stops** the existing process and proves `inactive/dead`, `MainPID=0` and process disappearance;
10. atomically switches `current`, installs only the reviewed persistent `90-release-runtime.conf`, reloads systemd and verifies the guarded effective runtime, ordered dual `ExecStartPre`, exact environment and restart limit;
11. **starts while still disabled and guarded**, then checks PID argv/cwd, `/proc/<pid>/environ`, source/runtime provenance, local/public health and the public login redirect;
12. writes and fsyncs `.pending-deploy-<release-id>.json`, then changes only the marker `status` from `switching` to `deploy_committed_pending_activation`; this is the logical commit point;
13. stops the guarded process, removes the `/run` guard, proves normal `Restart=on-failure` and unlimited runtime, then starts a new **unguarded but still disabled** process and repeats environment, provenance and health checks;
14. enables only after the unguarded checks pass, scans every symlink in all canonical systemd `.wants` and `.requires` directories by resolved target, and accepts exactly one root-owned `/etc/systemd/system/multi-user.target.wants/protocol-studio.service` link to the administrator base unit; a differently named alias to the same unit is rejected;
15. repeats runtime, source, PID/cwd, `/proc/<pid>/environ`, local/public health, login redirect and backup-evidence checks after enablement;
16. publishes the protected pending record as the final schema 5 passed deployment record, persists the final link and directory, unlinks the pending name and persists the directory again; only after that publication contract succeeds does it archive and fsync the active marker. A publication failure retains the marker for re-entrant recovery.

Before logical commit, a failure is fail-closed and recovery must restore the marker's recorded previous runtime. After `deploy_committed_pending_activation`, a failure remains fail-closed but recovery must finalize the committed release; it must not roll back to previous. The deployment script does not claim success merely because the guarded process answered health.

The switch includes a short planned service stop. The managed drop-in preserves `UMask=0077` and uses an explicit reset before the only writable path:

```ini
ReadWritePaths=
ReadWritePaths=/srv/apps/protocol-studio/shared
```

The empty assignment is required: without it, systemd list values from the base unit and drop-ins accumulate. The script verifies the effective value and refuses drift. It does not install or overwrite the base unit and never removes unrelated drop-ins; an unreviewed active drop-in is a refusal condition.

### Bounded runtime guard and reboot boundary

The transaction guard is deliberately placed under `/run/systemd/system`, so it is volatile and does **not** survive a reboot. While loaded it prevents automatic restart and limits the guarded process to 300 seconds. Before installing it, the scripts persistently disable the service and verify `systemctl is-enabled` stdout/exit status, `UnitFileState=disabled`, secure systemd directories and zero symlinks in every `.wants`/`.requires` directory whose canonical target is the service unit, regardless of the symlink basename. The enablement state and relevant directories are fsynced. Thus the persistent disablement survives even though the guard does not.

Do not treat that design as permission to reboot during a transaction. While `.deploy-transaction.json` exists, preserve the host state and run audited recovery. If an error path reports `FAIL-CLOSED CONFIRMED`, the script has read back disabled, inactive/dead, `MainPID=0`, disappearance of the original process and retention of the root-only marker. If it reports `FAIL-CLOSED NOT CONFIRMED`, the boundary is stricter: **DO NOT REBOOT**, do not delete/edit the marker or guard, and obtain manual systemd recovery before any further action.

The first legacy-to-release migration records the fixed legacy baseline `20260722-114300-620b1bcf9aa9`, the base-unit hash and the shared virtual-environment tree hash. A no-`.venv` rollback is allowed only to that registered baseline. Override `PROTOCOL_STUDIO_LEGACY_RELEASE_ID` only when a different baseline has been explicitly reviewed. This separate legacy path is the supported first-upgrade recovery boundary: before commit, recovery can return to the frozen shared-runtime baseline; after a schema 5 deployment succeeds, explicit rollback can still select that registered legacy baseline. It does not authorize activation of schema 2-4 release-local deployment records.

If `.deploy-transaction.json` exists, a prior operation is incomplete. Deploy and rollback refuse to continue. Do **not** delete or edit the marker. Run the frozen recovery control after reviewing the marker, its strict status, pending evidence, guard state and current host state:

```bash
sudo "$CONTROL/deploy/recover-transaction.sh" --confirm-recovery
```

Recovery validates the schema 3 marker, operation-specific key set, trusted backup and pending evidence. A release-local previous or activation target must resolve to strict schema 5 evidence and its canonical dual-gate drop-in; schema 2-4 markers fail before the service is disabled or stopped. The registered legacy shared-runtime marker shape remains independently supported. Direction is phase-dependent:

- `switching` or `rolling_back`: activate the marker's recorded previous runtime;
- `deploy_committed_pending_activation`: finalize that committed deployment target;
- `rollback_committed_pending_activation`: finalize that committed rollback target;
- `recovery_committed_pending_activation`: finish the target already committed by the earlier recovery.

Recovery applies the same persistent disablement and 300-second `/run` guard, runs a guarded private/production health and provenance sequence, creates or reuses only exact pending evidence, commits the recovery target when needed, removes the guard, starts a new unguarded process while disabled, validates it, enables only the unique canonical standard wants topology, and repeats full post-enable provenance/health checks. It then reconciles or publishes the original committed operation record when applicable and the recovery passed record, completing final fsync/pending unlink before archiving the active marker. Publication failure leaves the marker active, so rerunning recovery is supported and idempotent. If recovery cannot complete, its exit guard attempts real fail-closed state and retains the marker; `FAIL-CLOSED NOT CONFIRMED` means **DO NOT REBOOT** and requires manual systemd recovery.

## Explicit rollback

```bash
sudo "$CONTROL/deploy/rollback-release.sh" \
  --release-id <known-good-release-directory-name> \
  --confirm-rollback
```

Rollback first canaries and fingerprints the target as the real service user against an isolated database/runs copy. A modern target must have a strict schema 5 deployment record and the fixed external baseline/helper/fingerprint binding; schema 2-4 targets are rejected before database backup, marker creation or systemd mutation. Schema 5 targets retain the canonical managed per-release dual-gate drop-in; the registered legacy target removes only that drop-in and reuses the frozen shared virtual environment. It starts with `rolling_back`, then uses the same persistent-disable → 300-second guard → stop → switch → guarded start/check → pending record → `rollback_committed_pending_activation` → unguarded restart/check → unique canonical enablement → post-enable provenance/health → passed-record publication/fsync/pending unlink → marker archive discipline. A publication failure retains the active marker for re-entrant recovery. A precommit failure is recovered to the original runtime; after logical commit, recovery must finish the promised rollback target. It never removes a release, shared runs, the account database, backups or transaction evidence.

## Read-only health check

For a modern release, bind the check to the reviewed release Manifest by setting its lowercase digest explicitly. `check-production.sh` always runs `--verify-current` through the external helper, so a missing, conflicting or non-schema-5 baseline/helper/fingerprint binding fails; there is no schema 2-4 modern fallback. The checker defaults to `/srv/apps/protocol-studio`; an isolated staging root may be selected only with a canonical absolute `PROTOCOL_STUDIO_DEPLOY_ROOT` value. Relative paths, symlinks, hidden/dot components, `.`/`..`, repeated separators and trailing slashes are rejected, so a staging check cannot silently fall back to or alias the production root.

```bash
PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256='<64-lowercase-hex>' \
  "$CONTROL/deploy/check-production.sh"
```

Example for the dedicated staging tree:

```bash
PROTOCOL_STUDIO_DEPLOY_ROOT=/srv/apps/protocol-studio-staging \
PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256='<64-lowercase-hex>' \
  "$CONTROL/deploy/check-production.sh"
```

Local and public `/api/health` must both return the exact identity header and the report emits `release_identity=passed` or fails. A call with neither identity input fails closed. Availability-only compatibility checking requires an explicit, mutually exclusive opt-in:

```bash
PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY=true \
  "$CONTROL/deploy/check-production.sh"
```

That mode emits `release_identity=not_requested`; it is only for a deliberately registered legacy baseline and cannot approve a modern release. Every curl invocation disables `.curlrc`, bypasses proxies explicitly and runs after common proxy and `CURL_HOME` variables are cleared. A valid result still requires both health endpoints and the public login redirect to pass; listening sockets or `systemctl active` alone are insufficient.

Before production switching, perform a **read-only** query of the shared account database and confirm that the `PROTOCOL_STUDIO_ADMIN_USERNAME` from the EnvironmentFile already exists. Do not use an application start against the live database as this check: startup creates the configured bootstrap administrator when it is missing. Separately confirm that the configured scrypt bootstrap hash parses without changing the existing user's real credential or creating an unexpected administrator.

Production acceptance must additionally bind the running PID to the expected argv and `/proc/<pid>/cwd`, inspect effective systemd properties/drop-ins, then use a real existing account to verify login, old-session continuity, effective permissions and generation/download of all three deliverables: the environment-monitoring protocol workbook, alarm-state-word upload code and MCGS environment-monitoring device-import CSV. Health, the `/login` redirect and the validator's scrypt-prefix check do not prove those workflows.

## Environment file

Use `protocol-studio.env.example` only as a key/reference list. Never overwrite the existing production file during a deployment. Generate a password hash locally with `scripts/generate_password_hash.py`; do not put a real hash in source control.

## Human gates

Static repository checks do not prove a Docker build/run, staging or production systemd transaction behavior. In particular, Windows contract tests do not prove ordinary systemd restart integrity enforcement, `StartLimit` behavior, real `/proc/<pid>/environ`, ACL semantics, power-loss durability or recovery. A transient canary does not prove a production switch. Health endpoints do not prove authenticated generator workflows. Web and generator tests do not prove MCGS compilation, simulation or site correctness. Keep each of those as separate, recorded acceptance steps.
