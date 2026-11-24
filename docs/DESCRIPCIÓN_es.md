# apt 1.0: descripción

## Análisis

apt es el repositorio APT de los programas de Nicolas Vaughan que tienen un paquete para Debian: py-pdftools, py-slowdown, py-words y py-wk. Quien usa Debian o Ubuntu lo añade una vez, con su clave, y `apt upgrade` le trae cada versión nueva, como Copr en Fedora. Nació en noviembre de 2026: la publicación de py-pdftools ya hacía un `.deb`, pero solo se podía descargar a mano.

El equivalente habitual de Copr en Ubuntu, un PPA de Launchpad, solo acepta paquetes fuente y los construye sin internet; el paquete de py-pdftools lleva su propio Python, hecho a partir de su AppImage, porque las versiones anteriores de Ubuntu no tienen Python 3.14, y eso no puede construirse allí. De ahí el requisito: servir los paquetes que cada publicación ya construye y firma, con un índice firmado con la misma clave.

## Diseño

Es un repositorio «plano»: los paquetes y el índice (`Packages`, `Packages.gz`, `Release` y sus firmas `InRelease` y `Release.gpg`) van en una sola carpeta, que es la versión `stable` del repositorio nivaca/apt en GitHub. Un sitio de páginas no sirve: los de GitHub y Codeberg no admiten archivos de más de 100 MB, y el paquete de py-pdftools tiene 161. Los archivos de una versión pueden tener hasta 2 GB, y APT sigue la redirección con que GitHub los entrega.

De cada paquete y arquitectura queda solo la versión más nueva. Cada programa, al publicar, añade el suyo; el índice publicado es el estado, y no hay más que guardar.

## Implementación

Un solo archivo, `tools/apt_repo.py`, de unas 330 líneas de Python 3.14, sin más bibliotecas que las de Python; firma con GnuPG y publica con gh, la línea de órdenes de GitHub.

### Leer un paquete sin dpkg

Fedora no tiene dpkg. Un `.deb` es un archivo ar cuyo archivo de control va en un tar comprimido con gzip, xz o zstd; Python 3.14 lee zstd por sí mismo (`compression.zstd`).

### Las versiones

Se comparan como las compara dpkg: época, versión y revisión, por tramos de letras y de cifras, con la tilde antes que nada.

### Firmar y comprobar

El índice se firma con la clave de las versiones. Antes de subir nada, cada firma se comprueba como la comprobaría un usuario, solo con la clave pública, en una carpeta de GnuPG temporal, y las sumas del índice contra los archivos; si algo no cuadra, no se publica.

## Validación

Hay 16 pruebas (`uv run --no-project --with pytest python -m pytest tests`): el orden de las versiones como lo da dpkg, los paquetes leídos con cada compresión, el índice escrito, firmado con una clave hecha para la prueba (nunca la del autor) y comprobado con solo la pública, una versión nueva que reemplaza a la anterior y una más vieja que se deja fuera, y un archivo cambiado después de firmar, que se detecta.

Antes de publicarlo, se construyó con los cuatro paquetes en una carpeta servida por HTTP y se probó en contenedores de Ubuntu 24.04 y 26.04: APT aceptó la firma sin aviso; py-pdftools y py-slowdown se instalaron en los dos, y py-pdftools corrió; py-words, que necesita Python 3.13, solo en 26.04; py-wk pide Python 3.15, que ningún Ubuntu tiene todavía.

## Plataforma

El repositorio sirve a Debian 12, Ubuntu 22.04 y posteriores, en amd64, para los paquetes que traen su Python; los que usan el del sistema piden la versión que su paquete dice. La herramienta corre en Linux, con Python 3.14, gpg y gh; necesita internet para leer el índice publicado y para subir.

## Ambiente

Fue desarrollado en Fedora, con Python 3.14 y uv, en `~/Dropbox/dev/Python/apt`; el código está en https://github.com/nivaca/apt, y el repositorio, en los archivos de su versión `stable`. Para añadirlo: la clave (`nivaca-archive-keyring.gpg`) en `/usr/share/keyrings/` y la línea `deb [signed-by=/usr/share/keyrings/nivaca-archive-keyring.gpg] https://github.com/nivaca/apt/releases/download/stable ./` en `/etc/apt/sources.list.d/nivaca.list` (véase el README). Cada programa lo actualiza desde su propio script de publicación, con `tools/apt_repo.py add`.
