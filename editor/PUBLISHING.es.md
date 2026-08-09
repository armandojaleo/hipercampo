# Publicar el visor en VS Code Marketplace

[Read in English](PUBLISHING.md).

Esto es **aparte** de subir el código a git. Publicar en el Marketplace hace que
cualquiera lo instale con un clic desde VS Code. Requiere una cuenta de editor y un
token; son pasos que hace **el dueño** (tú), una sola vez. Mientras tanto, el `.vsix`
generado con `npx @vscode/vsce package` ya sirve para instalar a mano.

## Pasos de un solo uso (los haces tú)

1. **Crear un publisher.** Entra en <https://marketplace.visualstudio.com/manage> con
   una cuenta Microsoft. Crea un publisher con el ID **`armandojaleo`** (el mismo que
   está en `editor/package.json` → `"publisher"`). Si eliges otro ID, cámbialo también
   ahí.

2. **(Solo para CLI/CI) Crear un Personal Access Token (PAT).** Para una beta puedes
   saltarte esto y **subir el `.vsix` a mano** en la página del publisher (*+ New
   extension → Visual Studio Code*). Si aun así quieres token: en <https://dev.azure.com>
   → *User settings* → *Personal Access Tokens* → *New Token*:
   - Organization: **tu organización `armandojaleo`** (con ámbito de la org; **no** uses
     "All accessible organizations": esos PAT globales se retiran y dejan de funcionar el
     2026-12-01).
   - Scopes: **Show all scopes → Marketplace → Manage**.
   - Copia el token (no se vuelve a mostrar).

3. **Guardar el token como secreto del repo.** En GitHub → *Settings* → *Secrets and
   variables* → *Actions* → *New repository secret*:
   - Nombre: **`VSCE_PAT`**
   - Valor: el token del paso 2.

Con eso, el workflow de abajo publica solo.

## Publicar una versión

El workflow `.github/workflows/vsix.yml` publica al empujar un tag `viewer-vX.Y.Z`:

```bash
# la versión del tag debe coincidir con editor/package.json
git tag -a viewer-v0.9.19 -m "hipercampo viewer 0.9.19"
git push origin viewer-v0.9.19
```

Comprueba la versión: el tag debe coincidir con `editor/package.json`.

Antes de la primera publicación, confirma que existen el publisher `armandojaleo` y
el secreto de Actions (GitHub muestra el nombre, nunca el valor):

```bash
gh secret list --app actions
```

La salida debe incluir `VSCE_PAT`. Si no aparece, añádelo en **Settings → Secrets and
variables → Actions** antes de crear el tag. El workflow compila, ejecuta los contratos
de localización y los tests Playwright en Chromium antes de publicar.

## Publicar a mano (sin workflow)

```bash
cd editor
npm ci
npx playwright install chromium
npm run test:all
# Con VSCE_PAT cargado de forma segura en el entorno, sin pasarlo por argv:
npx @vscode/vsce publish
```

## Presentación antes de publicar

- El icono 128×128 y `galleryBanner` ya están integrados en `package.json`.
- El README incluye capturas actuales del Mapa y la Lista en tema oscuro.
- Revisar `LICENSE` (MIT del repo) y `repository` en `package.json`.
