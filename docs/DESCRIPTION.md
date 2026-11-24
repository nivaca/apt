How apt was made
================

apt is the APT repository of my programs that have a Debian package:
py-pdftools, py-slowdown, py-words and py-wk. With it, someone on Debian
or Ubuntu adds the repository once and `apt upgrade` brings each new
version, as Copr does on Fedora. I made it in November 2026, when
py-pdftools' release already built a `.deb` that could only be downloaded
by hand. Here I explain how it was made, in three stages.

It is licensed under the GNU General Public License, version 3 or later.
It uses only the Python standard library, GnuPG (GPL) to sign and check,
and GitHub's command line, gh (MIT), to publish.

Nicolas Vaughan is Associate Professor of Literature at the School of Arts
and Humanities of the Universidad de los Andes, Bogotá, Colombia.

1. Where it could live
----------------------

The usual equivalent of Copr for Ubuntu, a Launchpad PPA, takes only source
packages and builds them without internet; py-pdftools' package carries its
own Python, made from its AppImage, because older Ubuntu releases have no
Python 3.14, and that can't be built there. So the repository serves the
packages already built and signed by each release. A page site was the
first idea, but GitHub's and Codeberg's take no file over 100 MB, and the
package of py-pdftools has 161 MB. The files of a release on GitHub may
have up to 2 GB, and APT follows the redirection with which GitHub serves
them; so the repository is "flat", everything in one folder, and that
folder is the release `stable` of the repository nivaca/apt.

2. The tool
-----------

`tools/apt_repo.py add FILE.deb` reads the index already published, adds
the package (only the newest version of each package and architecture
stays, compared as dpkg compares versions), writes `Packages`,
`Packages.gz` and `Release`, and signs it as `InRelease` and `Release.gpg`
with the key of the releases. Before anything is uploaded, every signature
is checked as a user would check it, with only the public key, in a GnuPG
folder of its own, and the sums of the index against the files; then the
new files are uploaded and the replaced package deleted. A package is read
without dpkg, which Fedora doesn't have: a `.deb` is an ar archive whose
control file is in a tar compressed with gzip, xz or zstd, and Python
3.14 reads zstd itself.

3. Tried as a user would
------------------------

Before publishing it, I built the repository with the four packages in a
folder, served it over HTTP, and in containers of Ubuntu 24.04 and 26.04
added the key and the repository and installed each package. APT took the
signature without a warning. py-pdftools and py-slowdown installed on
both, and py-pdftools ran; py-words needs Python 3.13, so only on 26.04;
and py-wk asks for Python 3.15, which no Ubuntu has yet, so it installs
nowhere: its own package says so, not the repository.

Testing
-------

There are 16 tests (`uv run --no-project --with pytest python -m pytest
tests`): the order of versions as dpkg gives it, packages read with each
compression, the index written, signed with a key made for the test (never
mine) and checked with only the public one, a newer version replacing the
older and an older one left out, and a file changed after signing caught.
The program is one file of some 330 lines, and the tests some 120.
