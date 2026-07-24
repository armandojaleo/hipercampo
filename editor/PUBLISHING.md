# Publicar el visor en el Marketplace de VS Code

Esto es **aparte** de subir el código a git. Publicar en el Marketplace hace que
cualquiera lo instale con un clic desde VS Code. Requiere una cuenta de editor y un
token; son pasos que hace **el dueño** (tú), una sola vez. Mientras tanto, el `.vsix`
generado con `npx @vscode/vsce package` ya sirve para instalar a mano.

## Pasos de un solo uso (los haces tú)

1. **Crear un publisher.** Entra en <https://marketplace.visualstudio.com/manage> con
   una cuenta Microsoft. Crea un publisher con el ID **`armandojaleo`** (el mismo que
   está en `editor/package.json` → `"publisher"`). Si eliges otro ID, cámbialo también
   ahí.

2. **Crear un Personal Access Token (PAT).** En <https://dev.azure.com> → *User
   settings* → *Personal Access Tokens* → *New Token*:
   - Organization: **All accessible organizations**.
   - Scopes: **Marketplace → Manage**.
   - Copia el token (no se vuelve a mostrar).

3. **Guardar el token como secreto del repo.** En GitHub → *Settings* → *Secrets and
   variables* → *Actions* → *New repository secret*:
   - Nombre: **`VSCE_PAT`**
   - Valor: el token del paso 2.

Con eso, el workflow de abajo publica solo.

## Publicar una versión

El workflow `.github/workflows/vsix.yml` publica al empujar un tag `viewer-vX.Y.Z`:

```bash
# sube la versión en editor/package.json ("version": "0.2.0" -> "0.2.1")
git tag viewer-v0.2.1
git push origin viewer-v0.2.1
```

Comprueba la versión: el tag debe coincidir con `editor/package.json`.

## Publicar a mano (sin workflow)

```bash
cd editor
npm ci
npm run compile
npx @vscode/vsce publish -p <TU_PAT>
```

## Pendientes recomendados antes de publicar (no bloquean)

- **Icono de la extensión**: un PNG 128×128 en `editor/media/icon.png` y
  `"icon": "media/icon.png"` en `package.json`. El Marketplace lo muestra en la ficha.
  (El `brain.svg` actual es el de la barra de actividad, no vale como icono de ficha.)
- **`galleryBanner`** y capturas de pantalla en el README para que la ficha luzca.
- Revisar `LICENSE` (MIT del repo) y `repository` en `package.json`.
