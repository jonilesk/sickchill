# CLAUDE.md

Working notes for this checkout. Facts here were verified against the live host and this
repository on 2026-08-28 — re-check anything that looks stale rather than trusting it.

## What this repo is

A **fork** of [SickChill](https://github.com/SickChill/SickChill) (TV show automation: Tornado web
server, Mako templates, ConfigObj `.ini` config, SQLite). Python `>=3.10,<4.0`, version string
`2024.3.1`.

- `origin` = `https://github.com/jonilesk/sickchill` — **the only push target.** There is no
  upstream remote configured; do not push to or open PRs against SickChill/SickChill.
- Branch: `master`.

Two local commits sit on top of upstream `e1f8475de`:

| commit | what |
|---|---|
| `be4976136` | refuse to download or process executable payloads (`BLOCK_EXECUTABLE_FILES`, `payload_filter`) |
| `f727ff7b1` | TVmaze replaces Trakt as the show-discovery source; Trakt repaired behind a user-supplied key |

## Where the app actually runs

**Production: `joni@10.1.5.6`** (Ubuntu, Linux 6.8, x86_64). Passwordless SSH from this Mac works
(`ssh joni@10.1.5.6`).

- Web UI: **http://10.1.5.6:8081** — plain HTTP, `enable_https = 0`, `web_username = ""`, so it is
  **unauthenticated on the LAN**. Keep that in mind before exposing anything.
- Runs under Docker Compose, project `sickchill`, file `/home/docker/sickchill/docker-compose.yml`,
  `container_name: sickchill`, `restart: always`, `TZ=Europe/Helsinki`.
- Image: **`sickchill:exeblock`** (locally built, not from a registry).
- Container command: `sickchill --nolaunch --datadir /data --port 8081`.

Volumes (host → container):

| host | container | holds |
|---|---|---|
| `/home/docker/sickchill/data` | `/data` | **datadir** — `config.ini`, `sickchill.db`, `cache.db`, `Logs/` |
| `/home/docker/sickchill/config` | `/config` | legacy mount, effectively unused |
| `/home/docker/sickchill/sickchill-cache` | `/app/sickchill/sickchill/gui/slick/cache` | GUI image cache |
| `/media/Series` | `/media` | the library — SickChill's only root dir is `1\|/media` |
| `/media/Torrent` | `/downloads` | download landing area |

Notable live settings (read from `/data/config.ini`): `torrent_method = qbittorrent` pointing at
`https://10.1.5.6:8443/`, `nzb_method = blackhole`, `indexer_default = 1` (TheTVDB),
`use_trakt = 0`, `block_executable_files = 1`. Other containers on the same host that this one
works with: `jackett` (9117), `flaresolverr` (8191), `radarr` (7878).

**The running image predates the TVmaze commit.** Verified: `sickchill.show.recommendations.tvmaze`
raises `ModuleNotFoundError` inside the container, and `trakt_api_key` is absent from its
`config.ini`. `f727ff7b1` is pushed to the fork but **not deployed**.

## Deploying to 10.1.5.6

There is no source checkout on the host and no CI — the source is shipped as a tarball and built
there. The build installs a freshly built wheel *over* the official image
([contrib/Dockerfile.deploy](contrib/Dockerfile.deploy)) because building upstream's own Dockerfile
needs a Rust toolchain and a buildx builder with the `security.insecure` entitlement. Fine for
pure-Python changes; would not be for anything touching a compiled dependency.

```bash
SP=<scratchpad>; \
tar --exclude='.git' --exclude='node_modules' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='dist' --exclude='build' --exclude='.venv' --exclude='tests/*.db' \
    --exclude='.pytest_cache' -czf "$SP/sickchill-src.tar.gz" . && \
ssh joni@10.1.5.6 'mkdir -p /home/docker/sickchill-build/src && rm -rf /home/docker/sickchill-build/src/*' && \
scp -q "$SP/sickchill-src.tar.gz" joni@10.1.5.6:/home/docker/sickchill-build/ && \
ssh joni@10.1.5.6 'cd /home/docker/sickchill-build/src && tar xzf ../sickchill-src.tar.gz && \
  docker build -f contrib/Dockerfile.deploy -t sickchill:<newtag> .'
```

Then bump `image:` in `/home/docker/sickchill/docker-compose.yml` and
`cd /home/docker/sickchill && docker compose up -d`. Use a **new tag** per deploy so rollback is
just editing the tag back; `sickchill:exeblock` is the current good one.

Before the next deploy, two things will change on that box:

1. The new `cache.db` migration runs on first start (creates `tvmaze_premieres` and
   `tvmaze_refresh`; it does not rewrite existing tables). `cache.db` there is ~15 MB — back it up.
2. `TRAKT_API_KEY` now defaults to empty, so the Trakt tile disappears from `/addShows/` and any
   Trakt sync goes inert until a key is entered under Config → Notifications → Trakt.

## Local development

No poetry and no repo `.venv`. The working environment is an **editable** install (`sickchill.pth`,
107 packages, Python 3.14.6) living in a session scratchpad — so it disappears with the scratchpad.
Recreate with:

```bash
uv venv <scratchpad>/venv && <scratchpad>/venv/bin/python -m pip install -e . && \
<scratchpad>/venv/bin/python -m pip install pytest pytest-timeout pytest-cov mock ruff
```

Run a dev instance against a throwaway datadir — never against the production one:

```bash
V=<scratchpad>/venv/bin; DD=<scratchpad>/sc-datadir; mkdir -p $DD && \
nohup $V/python SickChill.py --nolaunch --port 8082 --datadir $DD > $DD/run.log 2>&1 &
```

`pkill` is unreliable for this; kill with `lsof -ti:8082 | xargs kill -9`. Startup takes ~25 s
before the UI answers. A stale datadir carries stale `config.ini` values — when testing anything
that depends on a *default*, use a fresh datadir, or you will be reading last run's saved value.

## Tests and lint

```bash
rm -f tests/cache.db tests/sickchill.db tests/failed.db && <venv>/bin/python -m pytest tests/ --no-cov -q
```

Wiping the test DBs is **mandatory, not hygiene**: cache.db migrations gate on `has_table`, so a
leftover `tests/cache.db` already satisfies the check and the new table is never created. Note
`rm -f tests/*.db` fails under zsh (`no matches found`) when nothing matches — list the files.
Baseline as of `f727ff7b1`: 342 passed, 143 skipped, 5 xfailed.

Lint (line length 160, `builtins = ["_"]`):

```bash
<venv>/bin/ruff format --check . && <venv>/bin/ruff check sickchill tests SickChill.py
```

`pyproject.toml` defines poe tasks (`poe test`, `poe lint`, `poe babel-extract`, …) but poe is not
installed here; the commands above are the ones actually used.

## Codebase things that will bite

- **Mako does not auto-escape in this app.** `TemplateLookup` sets no `default_filters`, so `${}`
  renders raw. Any remote text needs an explicit `| h`, any URL `| u`. Some existing templates
  (e.g. `trendingShows.mako`) quietly assume otherwise — do not copy that.
- **cache.db migrations are a subclass chain, not a list.** `_process_upgrade` recurses via
  `__subclasses__()`, so a new migration must subclass the *current tail* class in
  [databases/cache.py](sickchill/oldbeard/databases/cache.py). Appending a standalone class does
  nothing.
- **Shows are keyed on a TheTVDB id.** `ShowIndexer` registers only indexer 1 and `tv_shows` is
  keyed on that `indexer_id`, so anything without a TVDB id cannot be added at all. This is why the
  TVmaze list hides ~44 % of upcoming premieres rather than showing unaddable cards.
- **Every public method on a `@Route` handler is automatically a route**
  ([views/index.py:145](sickchill/views/index.py:145)) — adding a method adds a URL. Handlers run
  `@run_on_executor`, so blocking work there does not stall the IO loop.
- **A new setting needs four touchpoints**: default in `settings.py`, read in `start.py
  initialize()`, written in `start.py save_config()`, plus the config view and its `.mako`. Miss one
  and it silently fails to persist.
- **`helpers.make_session()` wraps the session in `CacheControl` backed by an in-memory dict** — do
  not use it for large payloads (the TVmaze `/schedule/full` body is ~12 MB and would be pinned for
  the process lifetime).
- **`$.loadTraktImages()` selects `img.trakt-image`** and blanks any such image lacking
  `data-src-indexer-id`. The TVmaze cards deliberately use `trakt-image-static`; renaming it back to
  match the Trakt template would blank every poster.
- **`core.js` is not what the browser gets.** [layouts/main.mako:405](sickchill/gui/slick/views/layouts/main.mako:405)
  serves `js/core.js` only when `settings.DEVELOPER` is on; every normal install (including the
  container on 10.1.5.6, where `developer = 0`) gets the committed `js/core.min.js`, built by
  `grunt uglify:core` from [Gruntfile.js:202](Gruntfile.js:202). Editing `core.js` alone therefore
  changes nothing in production, and `UTIL.exec` skips a missing action **silently**, so the symptom
  is a blank page with a clean console. Either rebuild the minified bundle or ship page JS as its own
  file (`js/trendingShows.js`, `js/upcomingShows.js`) included from the template.
- **`$.fn.loadRemoteShows`, `$.initRemoteShowGrid` and the `SICKCHILL` namespace are defined inside
  core.js's locale `$.getJSON` callback**, so they do not exist when a page's own script is parsed.
  Wait for them rather than assuming document-ready is late enough.
- **Locale `.po`/`.pot` files are generated** by `poe babel-extract` — never hand-edit. Just wrap
  new user-facing strings in `_()`.

## Conventions

- Commit or push only when asked. End commit messages with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- TVmaze data is CC BY-SA 4.0 — the "Data provided by TVmaze" attribution and the per-card links to
  `tvmaze_url` are a licence condition, not decoration. Do not remove them.
