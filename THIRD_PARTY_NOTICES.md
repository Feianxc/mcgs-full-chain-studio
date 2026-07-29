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

| Package | Production pin | Declared license |
| --- | --- | --- |
| FastAPI | 0.140.7 | MIT |
| [Starlette](https://www.starlette.io/) | 1.3.1 | BSD-3-Clause |
| Uvicorn | 0.38.0 | BSD-3-Clause |
| Pydantic | 2.12.5 | MIT |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| openpyxl | 3.1.2 | MIT |

Each installed distribution may bring transitive dependencies. Release operators must preserve the license metadata shipped in the environment or container and should generate a dependency inventory for the exact build.

## Excluded proprietary materials

This repository and its release packages do **not** include MCGS software, MCGS help documentation, license files, project/template binaries, customer engineering data, or other materials for which redistribution rights have not been verified.
