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

## Temporary dependency-audit risk

The required Node 24.15.0/npm 12.0.1 installation currently reports 12
`high` and 0 `critical` findings (`npm audit --json`, 2026-07-28). The affected
dependency families and installed paths are:

- Next's nested `node_modules/next/node_modules/postcss@8.4.31`, covered by
  GHSA-qx2v-qp2m-jg93, GHSA-6g55-p6wh-862q, and GHSA-r28c-9q8g-f849.
- `node_modules/sharp@0.34.5`, which inherits the libvips advisory
  GHSA-f88m-g3jw-g9cj.
- The ESLint chain (`eslint`, `eslint-config-next`, and its import, JSX
  accessibility, and React plugins), whose nested
  `minimatch@3.1.5`/`brace-expansion@1.1.16` paths are covered by
  GHSA-mh99-v99m-4gvg. The direct `next` and `eslint-config-next` entries
  report these transitive findings.

`npm audit fix` is not an acceptable mitigation for this increment: the
current report proposes incompatible major changes, including
`next@9.3.3` and `eslint-config-next@0.2.4`, rather than patched releases
within the declared 16.x compatibility bands. No audit fix, dependency
override, or version change is introduced here.

The user explicitly accepted this risk temporarily on 2026-07-28. The scope
is the foundation runtime setup and its local/development dependency tree;
this is not a production security sign-off. The product maintainer owns the
acceptance. It must be reviewed before beta or production use, and whenever
compatible patched releases become available. The exit condition is to remove
this acceptance after all affected paths can be upgraded within the supported
compatibility bands and the resulting audit is re-verified.

The T002 native-script policy remains narrow and unrelated to this acceptance:
only the pinned packages `sharp@0.34.5` and `unrs-resolver@1.12.2` are
allowlisted. No other install scripts are permitted by the policy.
