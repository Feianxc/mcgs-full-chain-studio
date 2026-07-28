# Contributing

Thank you for improving MCGS Full-Chain Studio.

## Before you start

- Search existing issues and keep each change focused.
- Use synthetic, non-customer examples.
- Do not submit MCGS software, help files, `.MCP` projects, template binaries, customer spreadsheets, screenshots, generated runs, credentials or production configuration.
- Confirm that you have the right to license your contribution under Apache-2.0.

By intentionally submitting a contribution for inclusion, you agree that it is provided under the Apache License 2.0, unless it is conspicuously marked “Not a Contribution.”

## Development setup

```bash
python -m venv .venv
python -m pip install -r requirements.dev.txt
python scripts/run_tests.py
```

Node.js 20+ is required for the JavaScript checks.

## Pull-request checklist

1. Keep project defaults neutral and customer-independent.
2. Add or update automated tests for behavior changes.
3. Run:

   ```bash
   python scripts/validate_repository.py
   python scripts/check_public_tree.py --root .
   python scripts/run_tests.py
   python packaging/build_release.py --version 0.0.0-pr --check-only
   ```

4. Confirm that no real path, project name, topology, point table or secret is present.
5. Explain any MCGS-specific behavior and its manual verification boundary.
6. Update `CHANGELOG.md` for user-visible changes.

## Structured data rules

- Preserve JSON types: numbers, booleans, `null` and arrays must not be stringified.
- Empty, one-item and many-item collections must keep the same array contract.
- Schema and seed changes require a parse test and a representative synthetic fixture.
- Generated manifests must contain only normalized relative paths.

## MCGS change rules

Generated guidance must be based on explicit topology and mapping inputs. It must not claim to have modified, compiled, simulated or accepted an `.MCP` file unless that exact action was independently performed and evidenced.

## License and provenance

Record the origin and license of any third-party code or asset in `THIRD_PARTY_NOTICES.md`. Do not copy content merely because it is publicly accessible.
