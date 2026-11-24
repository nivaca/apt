El repositorio APT de los programas de Nicolas Vaughan
=====================================================

Los paquetes para Debian y Ubuntu de mis programas, en un solo repositorio
APT firmado: [py-pdftools](https://github.com/nivaca/py-pdftools),
[py-slowdown](https://github.com/nivaca/py-slowdown),
[py-words](https://github.com/nivaca/py-words) y
[py-wk](https://github.com/nivaca/py-wk). Se añade una vez, y `apt upgrade`
trae cada versión nueva.

Añadirlo
--------

    sudo curl -fsSLo /usr/share/keyrings/nivaca-archive-keyring.gpg \
        https://github.com/nivaca/apt/releases/download/stable/nivaca-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/nivaca-archive-keyring.gpg] https://github.com/nivaca/apt/releases/download/stable ./" \
        | sudo tee /etc/apt/sources.list.d/nivaca.list
    sudo apt update
    sudo apt install py-pdftools

La clave es la que firma cada versión de estos programas (su huella es
`8187 0643 CA22 1AF9 0C30  554E BE68 32CD 3599 4948`); la misma clave, en
texto, es `nivaca-archive-keyring.asc` en este repositorio.

Lo que necesita cada paquete: py-pdftools y py-slowdown traen su propio
Python (Debian 12, Ubuntu 22.04 y posteriores); py-words necesita Python
3.13 o posterior (Ubuntu 26.04, Debian 13); py-wk, Python 3.15.

Cómo se hace
------------

El repositorio es «plano»: los paquetes y el índice (`Packages`,
`Packages.gz`, `Release` y sus firmas `InRelease` y `Release.gpg`) son los
archivos de la versión `stable` de este repositorio, porque un sitio de
páginas no admite archivos de más de 100 MB, y el paquete de py-pdftools
es más grande. Cada programa, al publicar una versión, añade su paquete con
`tools/apt_repo.py add ARCHIVO.deb`: solo queda la versión más nueva de cada
paquete, el índice se firma, cada firma se comprueba solo con la clave
pública antes de subir nada, y el paquete reemplazado se borra.
`uv run --no-project --with pytest python -m pytest tests` corre sus
pruebas, que firman con una clave propia, nunca con la mía.

Licencia: GNU General Public License, versión 3 o posterior
(GPL-3.0-or-later). Nicolas Vaughan <nicolasvaughan@proton.me>.
