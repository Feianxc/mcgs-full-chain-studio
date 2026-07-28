# Security policy

## Supported versions

Until the first stable release, security fixes are provided only for the latest commit on the default branch and the latest published release.

## Report a vulnerability

Do not open a public issue for a suspected vulnerability, exposed credential, customer data, or production access detail.

Use GitHub's **Private vulnerability reporting** feature for this repository. Include:

- affected version or commit;
- reproduction steps with synthetic data only;
- expected and actual behavior;
- impact and suggested mitigation;
- whether any credential or personal/customer data may have been exposed.

Do not include real passwords, session cookies, generated customer files, production database copies, or other secrets in the report. Maintainers should acknowledge a valid report as soon as practical and coordinate disclosure after a fix is available.

## Production security requirements

An Internet-facing deployment must:

1. enable `PROTOCOL_STUDIO_AUTH_ENABLED`;
2. use a unique, locally generated password hash;
3. store `PROTOCOL_STUDIO_SECURITY_DB` and `PROTOCOL_STUDIO_RUNS_ROOT` outside the release directory;
4. use HTTPS and secure cookies;
5. restrict `PROTOCOL_STUDIO_ALLOWED_HOSTS`;
6. preserve CSRF protection for all state-changing endpoints;
7. run as an unprivileged service account;
8. protect the environment file and shared database with operating-system permissions;
9. back up the SQLite database before a production switch;
10. keep the previous release available for rollback.

The included deployment workflow does not modify DNS or Cloudflare and must not reset the account database.

## Secret handling

- Never commit `.env`, a real password hash, private keys, access tokens, cookies, SQLite files, or generated runs.
- Treat password hashes as credentials even though they are not plaintext.
- Rotate a credential immediately if it appears in Git history; deleting the latest copy is not sufficient.
- Use repository secret scanning and the local `scripts/check_public_tree.py` gate before release.

## Scope and verification boundary

A passing code scan or web security test does not prove that a generated MCGS change is safe in a live installation. MCGS compilation, simulation, device commissioning, alarm verification and site acceptance remain separate, manual release gates.
