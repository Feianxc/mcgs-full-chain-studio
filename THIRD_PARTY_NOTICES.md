# Third-party notices

This file is informational and does not replace the applicable license text.

## Vendored browser asset

### Lucide

- Component: `protocol_studio/static/vendor/lucide/lucide.min.js`
- Project: <https://lucide.dev/>
- License: ISC; a subset of icons derived from Feather is MIT
- Complete notices: [`protocol_studio/static/vendor/lucide/LICENSE`](protocol_studio/static/vendor/lucide/LICENSE)

The vendored license file must remain in source and binary distributions that include Lucide.

## Runtime Python dependencies

The production environment installs these packages from their respective distributors; their source is not copied into this repository:

| Package | Declared license |
| --- | --- |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| Pydantic | MIT |
| Jinja2 | BSD-3-Clause |
| openpyxl | MIT |

Each installed distribution may bring transitive dependencies. Release operators must preserve the license metadata shipped in the environment or container and should generate a dependency inventory for the exact build.

## Excluded proprietary materials

This repository and its release packages do **not** include MCGS software, MCGS help documentation, license files, project/template binaries, customer engineering data, or other materials for which redistribution rights have not been verified.
