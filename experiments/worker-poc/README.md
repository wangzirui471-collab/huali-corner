# Isolated Python Worker platform probe

This experiment uses only local D1/R2 bindings (`remote: false`) and a unique
Worker name. It does not import production IDs or credentials. Do not deploy it.

From this directory, install Python 3.13 and `uv`, then run:

```powershell
$env:PYTHONUTF8 = '1'
uv sync --locked
npm ci
uv run python sync_sources.py
uv run pywrangler d1 execute huali-refactor-local-poc --local --file schema.sql
uv run pywrangler dev --test-scheduled
```

In another shell run `uv run python smoke.py`. It checks `/api/health`, D1 rollback,
20-row JSON1/batch behavior, R2, duplicate local Cron, the synthetic 600000-round
legacy KDF vector, API/media 404 responses and SPA deep links.
Record actual results in
`docs/refactor/verification.md`; an isolated real Cloudflare environment is a
separate gate. The test endpoints use synthetic local data only.

`sync_sources.py` copies only the real image adapter and its error types into an
ignored local source folder. This keeps the probe and new API on the same image
algorithm. Pillow packaging and `/api/probe/image` are additional platform gates;
the probe does not provide authentication or a production media endpoint.

On Windows, UTF-8 mode is required because workers-py 1.17.8 otherwise reads a
Chinese-path pyvenv.cfg using the system GBK codec. Pillow 12.3.0 did not resolve
for this SDK's Emscripten index. The probe pins 12.2.0 and has actually executed
`uv run python image_smoke.py` successfully, including EXIF, 20M synthetic pixels,
5 MiB padded JPEG, invalid/animated input rejection and R2 round trips.

This is a local capability result. Pillow 12.3.0 contains security fixes missing
from the probe version; the formal API remains on 12.3.0. Do not promote 12.2.0
to production based on this test. See
`docs/refactor/decisions/0005-worker-image-runtime.md` for the runtime decision
and remaining cloud CPU/memory, concurrency and authenticated-media gates.
