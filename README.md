The APT repository of Nicolas Vaughan's programs
=================================================

The Debian and Ubuntu packages of my programs, in one signed APT
repository: [py-pdftools](https://github.com/nivaca/py-pdftools),
[py-slowdown](https://github.com/nivaca/py-slowdown),
[py-words](https://github.com/nivaca/py-words) and
[py-wk](https://github.com/nivaca/py-wk). Add it once, and `apt upgrade`
brings each new version.

Adding it
---------

    sudo curl -fsSLo /usr/share/keyrings/nivaca-archive-keyring.gpg \
        https://github.com/nivaca/apt/releases/download/stable/nivaca-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/nivaca-archive-keyring.gpg] https://github.com/nivaca/apt/releases/download/stable ./" \
        | sudo tee /etc/apt/sources.list.d/nivaca.list
    sudo apt update
    sudo apt install py-pdftools

The key is the one that signs every release of these programs (its
fingerprint is `8187 0643 CA22 1AF9 0C30  554E BE68 32CD 3599 4948`); the
same key, armored, is `nivaca-archive-keyring.asc` in this repository.

What each package needs: py-pdftools and py-slowdown bring their own
Python (Debian 12, Ubuntu 22.04 and later); py-words needs Python 3.13 or
later (Ubuntu 26.04, Debian 13); py-wk needs Python 3.15.

How it is made
--------------

The repository is "flat": the packages and the index (`Packages`,
`Packages.gz`, `Release`, and its signatures `InRelease` and
`Release.gpg`) are the files of the release `stable` of this repository,
since a page site doesn't take files over 100 MB, and the package of
py-pdftools is larger. Each program, when it publishes a version, adds its
package with `tools/apt_repo.py add FILE.deb`: only the newest version of
each package stays, the index is signed, every signature is checked with
only the public key before anything is uploaded, and the package replaced
is deleted. `uv run --no-project --with pytest python -m pytest tests`
runs its tests, which sign with a key of their own, never mine.

Licence: GNU General Public License, version 3 or later
(GPL-3.0-or-later). Nicolas Vaughan <nicolasvaughan@proton.me>.
