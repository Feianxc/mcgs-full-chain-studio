from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("MCGS_STUDIO_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("MCGS_STUDIO_PORT", "8123"))
    uvicorn.run("protocol_studio.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
