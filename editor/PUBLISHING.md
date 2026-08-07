# Publish the viewer to VS Code Marketplace

Publishing the extension is separate from pushing the repository. A generated `.vsix`
can always be installed manually; Marketplace publication additionally needs a publisher
account and token. [Leer en español](PUBLISHING.es.md).

## Simplest path: upload the .vsix by hand (no token)

For a beta this is the least friction — no PAT, no CI secret:

1. Open <https://marketplace.visualstudio.com/manage> with a Microsoft account and create
   the **`armandojaleo`** publisher, matching `publisher` in `package.json`.
2. `npx @vscode/vsce package` (see below), then on the publisher page choose
   **+ New extension → Visual Studio Code** and upload the generated `.vsix`.
3. Updates: re-package and upload again (or **Update** on the existing extension).

Because `package.json` sets `"preview": true`, the listing shows a **Preview** badge.

## Token setup (only needed for CLI/CI publishing)

1. Create the `armandojaleo` publisher as above.
2. At <https://dev.azure.com>, create a Personal Access Token with:
   - Organization: **your `armandojaleo` organization** (scope it to the org — do **not**
     use "All accessible organizations": those global PATs are being retired and stop
     working on 2026-12-01).
   - Scope: **Show all scopes → Marketplace → Manage**.
3. Add the token to the GitHub repository as the **`VSCE_PAT`** Actions secret.

Never commit or paste the token into source files, issues or logs. For long-term CI, the
future-proof route is short-lived Microsoft Entra auth (e.g. `azure/login` via OIDC in
Actions) rather than a static PAT.

## Automated release

The `.github/workflows/vsix.yml` workflow publishes tags shaped as `viewer-vX.Y.Z`.
The tag must exactly match `editor/package.json`:

```bash
git tag viewer-v0.9.10
git push origin viewer-v0.9.10
```

Before publishing, the workflow installs locked dependencies, compiles TypeScript, runs
the localization/icon contract, checks the tag version and only then calls `vsce publish`.

## Build and inspect locally

```bash
cd editor
npm ci
npm test
npx @vscode/vsce package
npx @vscode/vsce ls
```

Install the resulting file through **Extensions → … → Install from VSIX…**. Verify both
an English and Spanish VS Code profile before creating the release tag.

The Marketplace icon is `media/icon.png` (128×128) and the Activity Bar uses the
theme-aware monochrome `media/brain.svg`. The next presentation improvement is adding
current screenshots to the Marketplace README.
