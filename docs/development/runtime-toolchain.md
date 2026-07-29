# Runtime toolchain verification

This worktree was verified with the committed `uv.lock` and `package-lock.json`.
The lockfiles and their corresponding manifests were not resolved, updated, or
rewritten.

## Verified versions

- Python: `3.13.14` (satisfies `>=3.13,<3.14`)
- uv: `0.12.0`
- Node: `v24.15.0`, invoked from
  `C:\Users\Usuario\AppData\Local\nvm\v24.15.0\node.exe`
- npm: `12.0.1`, invoked from its cached CLI at
  `C:\Users\Usuario\AppData\Local\npm-cache\_npx\0636ef6846913eae\node_modules\npm\bin\npm-cli.js`

## Frozen installation commands

From the repository root, run the Python installation without changing the
lockfile:

```powershell
python -m uv sync --frozen --all-groups
```

Run the JavaScript installation with the isolated Node runtime and cached npm
CLI. npm 12's registry security default requires the command-scoped
`--allow-remote=all` flag in this host:

```powershell
$node = 'C:\Users\Usuario\AppData\Local\nvm\v24.15.0\node.exe'
$npmCli = 'C:\Users\Usuario\AppData\Local\npm-cache\_npx\0636ef6846913eae\node_modules\npm\bin\npm-cli.js'
& $node $npmCli ci --allow-remote=all
```

The successful commands left `uv.lock` and `package-lock.json` byte-for-byte
unchanged. The tracked-input check was:

```powershell
git diff --exit-code -- uv.lock package-lock.json pyproject.toml package.json apps/web/package.json
```

## Generated local artifacts

`uv sync` creates `.venv` in the repository root for the local Python runtime
and all dependency groups. `npm ci` creates the ignored root `node_modules`
tree, including the `@umbral/web` workspace link and its resolved workspace
dependencies. Neither directory is committed. To rebuild them, remove only
these generated directories and re-run the two frozen commands above; do not
run `uv lock`, `npm install`, or edit either lockfile as part of this workflow.

## Host gap

Docker and Docker Compose are not installed on this host. Consequently, T005
runtime container validation was not performed here. This verification does
not claim lint, typecheck, build, tests, Docker, or four-surface startup.
