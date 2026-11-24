#!/usr/bin/env python3
"""El repositorio APT de los programas de Nicolas Vaughan (py-pdftools, py-slowdown, py-wk, py-words...): un
repositorio «plano» (todo en una carpeta: los .deb, Packages, Packages.gz, Release, InRelease y Release.gpg),
publicado como los archivos de la versión «stable» de github.com/nivaca/apt. Las páginas de GitHub y de
Codeberg no admiten archivos de más de 100 MB, y el .deb de py-pdftools los pasa; los archivos de una versión
pueden tener hasta 2 GB, y APT sigue la redirección con que GitHub los entrega.

Cada programa, al publicar una versión, llama a «add» con su .deb: se lee el índice que ya está publicado, el
paquete entra (o reemplaza la versión anterior del mismo nombre y arquitectura: solo queda la más nueva), el
índice se escribe y se firma con la clave de las versiones, y cada firma se comprueba como la comprobaría un
usuario, solo con la clave pública, en una carpeta de GnuPG temporal; si una no se verifica, no se publica
nada. Después se suben los archivos nuevos y se borran los .deb reemplazados.

Solo usa la biblioteca de Python (3.14: el módulo compression.zstd lee los .deb comprimidos con zstd), gpg y,
para publicar, gh. Un usuario lo añade así (véase el README):

    deb [signed-by=/usr/share/keyrings/nivaca-archive-keyring.gpg] \\
        https://github.com/nivaca/apt/releases/download/stable ./
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = "nivaca/apt"
TAG = "stable"
KEY = "81870643CA221AF90C30554EBE6832CD35994948"  # (the key of every release, as in each packaging/build-rpm.sh)
ROOT = Path(__file__).resolve().parent.parent
PUBLIC_ASC = ROOT / "nivaca-archive-keyring.asc"
PUBLIC_GPG = ROOT / "nivaca-archive-keyring.gpg"
INDEX = ("Packages", "Packages.gz", "Release", "InRelease", "Release.gpg")
# Los campos de control que van en Packages, en este orden (los demás del .deb siguen, como vienen)
FIRST = ("Package", "Version", "Architecture", "Maintainer", "Installed-Size", "Depends", "Pre-Depends",
         "Recommends", "Suggests", "Conflicts", "Breaks", "Replaces", "Provides", "Section", "Priority",
         "Homepage")
URL = f"https://github.com/{REPO}/releases/download/{TAG}"


class RepoError(Exception):
    pass


# ----------------------------------------------------------------- reading a .deb

def _ar_members(data: bytes) -> dict[str, bytes]:
    """The members of an ar archive (a .deb is one), by name."""
    if not data.startswith(b"!<arch>\n"):
        raise RepoError("not a .deb (no ar archive)")
    out, at = {}, 8
    while at + 60 <= len(data):
        header = data[at:at + 60]
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        at += 60
        out[name] = data[at:at + size]
        at += size + (size % 2)  # (los miembros van alineados a dos bytes)
    return out


def _untar(name: str, blob: bytes) -> tarfile.TarFile:
    if name.endswith(".zst"):
        from compression import zstd

        return tarfile.open(fileobj=io.BytesIO(zstd.decompress(blob)), mode="r:")
    return tarfile.open(fileobj=io.BytesIO(blob), mode="r:*")  # (.gz, .xz, or none)


def control_of(path: Path) -> dict[str, str]:
    """The fields of the control file of the .deb at PATH (multi-line values kept as they are written)."""
    members = _ar_members(path.read_bytes())
    name = next((n for n in members if n.startswith("control.tar")), None)
    if name is None:
        raise RepoError(f"{path.name}: no control.tar in it")
    with _untar(name, members[name]) as tar:
        member = next((m for m in tar.getmembers() if m.name.lstrip("./") == "control"), None)
        if member is None:
            raise RepoError(f"{path.name}: no control file")
        text = tar.extractfile(member).read().decode("utf-8")
    return parse_stanza(text)


def parse_stanza(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    last = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and last:  # (continuación de un campo de varias líneas)
            fields[last] += "\n" + line
            continue
        key, _, value = line.partition(":")
        last = key.strip()
        fields[last] = value.strip()
    return fields


def parse_packages(text: str) -> list[dict[str, str]]:
    return [parse_stanza(block) for block in re.split(r"\n\s*\n", text) if block.strip()]


def stanza(fields: dict[str, str]) -> str:
    keys = [k for k in FIRST if k in fields] + [k for k in fields if k not in FIRST]
    return "".join(f"{k}: {fields[k]}\n" for k in keys)


def entry(path: Path) -> dict[str, str]:
    """The stanza of Packages for the .deb at PATH: its control fields, its file name and its sums."""
    fields = control_of(path)
    data = path.read_bytes()
    fields["Filename"] = path.name  # (plano: junto al índice)
    fields["Size"] = str(len(data))
    fields["MD5sum"] = hashlib.md5(data).hexdigest()
    fields["SHA1"] = hashlib.sha1(data).hexdigest()
    fields["SHA256"] = hashlib.sha256(data).hexdigest()
    return fields


# ----------------------------------------------------------------- Debian versions

def _order(c: str) -> int:
    if c == "~":
        return -1
    if c.isdigit():
        return 0
    if c.isalpha():
        return ord(c)
    return ord(c) + 256


def _compare_part(a: str, b: str) -> int:
    """dpkg's comparison of an upstream version or a revision: runs of non-digits, then of digits."""
    while a or b:
        na = re.match(r"[^\d]*", a).group(0)
        nb = re.match(r"[^\d]*", b).group(0)
        for x, y in zip(na + "\0" * (len(nb) - len(na)), nb + "\0" * (len(na) - len(nb))):
            ox = 0 if x == "\0" else _order(x)
            oy = 0 if y == "\0" else _order(y)
            if ox != oy:
                return -1 if ox < oy else 1
        a, b = a[len(na):], b[len(nb):]
        da = re.match(r"\d*", a).group(0)
        db = re.match(r"\d*", b).group(0)
        if int(da or 0) != int(db or 0):
            return -1 if int(da or 0) < int(db or 0) else 1
        a, b = a[len(da):], b[len(db):]
    return 0


def compare_versions(a: str, b: str) -> int:
    """-1, 0 or 1, as dpkg --compare-versions orders A and B (epoch, upstream version, revision)."""
    def split(v):
        epoch, _, rest = v.rpartition(":") if ":" in v else ("0", "", v)
        upstream, _, revision = rest.rpartition("-") if "-" in rest else (rest, "", "0")
        return int(epoch or 0), upstream, revision

    ea, ua, ra = split(a)
    eb, ub, rb = split(b)
    if ea != eb:
        return -1 if ea < eb else 1
    return _compare_part(ua, ub) or _compare_part(ra, rb)


# ----------------------------------------------------------------- the index

def merge(existing: list[dict[str, str]], new: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """EXISTING with NEW added: for each package and architecture, only the newest version stays. Returns the
    stanzas, sorted, and the file names that are no longer in the index (to remove)."""
    best: dict[tuple[str, str], dict[str, str]] = {}
    for fields in existing + new:
        key = (fields["Package"], fields["Architecture"])
        old = best.get(key)
        if old is None or compare_versions(fields["Version"], old["Version"]) >= 0:
            best[key] = fields
    kept = sorted(best.values(), key=lambda f: (f["Package"], f["Architecture"]))
    names = {f["Filename"] for f in kept}
    gone = sorted({f["Filename"] for f in existing} - names)
    return kept, gone


def write_index(folder: Path, stanzas: list[dict[str, str]], key: str, gnupghome: str | None = None,
                now: dt.datetime | None = None) -> None:
    """Packages, Packages.gz, Release (with the sums of both), and its signatures InRelease and Release.gpg,
    made with KEY, in FOLDER."""
    text = "\n".join(stanza(f) for f in stanzas)
    (folder / "Packages").write_text(text, encoding="utf-8")
    with gzip.GzipFile(folder / "Packages.gz", "wb", mtime=0) as gz:
        gz.write(text.encode("utf-8"))
    now = now or dt.datetime.now(dt.UTC)
    arches = sorted({f["Architecture"] for f in stanzas}) or ["amd64", "all"]
    lines = ["Origin: nivaca", "Label: nivaca", f"Suite: {TAG}", f"Codename: {TAG}",
             f"Date: {now.strftime('%a, %d %b %Y %H:%M:%S UTC')}", f"Architectures: {' '.join(arches)}",
             "Description: The programs of Nicolas Vaughan (py-pdftools, py-slowdown, py-wk, py-words)"]
    for title, algorithm in (("MD5Sum", hashlib.md5), ("SHA256", hashlib.sha256)):
        lines.append(f"{title}:")
        for name in ("Packages", "Packages.gz"):
            data = (folder / name).read_bytes()
            lines.append(f" {algorithm(data).hexdigest()} {len(data):>16} {name}")
    (folder / "Release").write_text("\n".join(lines) + "\n", encoding="utf-8")
    env = dict(os.environ, **({"GNUPGHOME": gnupghome} if gnupghome else {}))
    for args, out in ((["--clearsign"], "InRelease"), (["--detach-sign", "--armor"], "Release.gpg")):
        (folder / out).unlink(missing_ok=True)
        subprocess.run(["gpg", "--batch", "--yes", "--local-user", key, "--digest-algo", "SHA512", *args,
                        "--output", str(folder / out), str(folder / "Release")], check=True, env=env)


def verify(folder: Path, public_key: Path) -> None:
    """Every signature checked as a user would check it, with only PUBLIC_KEY, in a GnuPG folder of its own;
    and the sums of Release against the files, and those of Packages against the .deb files that are here.
    RepoError at the first that fails."""
    with tempfile.TemporaryDirectory(prefix="apt-verify-", dir="/tmp") as home:
        def gpg(*args):
            return subprocess.run(["gpg", "--batch", "--homedir", home, *args], capture_output=True, text=True)

        if gpg("--import", str(public_key)).returncode != 0:
            raise RepoError(f"the public key {public_key} can't be read")
        for args in (["--verify", str(folder / "InRelease")],
                     ["--verify", str(folder / "Release.gpg"), str(folder / "Release")]):
            done = gpg(*args)
            if done.returncode != 0 or "Good signature" not in done.stderr:
                raise RepoError(f"a signature doesn't verify: {' '.join(args)}\n{done.stderr}")
    release = parse_stanza((folder / "Release").read_text(encoding="utf-8"))
    for line in release["SHA256"].splitlines():
        if line.strip():
            digest, size, name = line.split()
            data = (folder / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest or len(data) != int(size):
                raise RepoError(f"{name} doesn't match its sum in Release")
    for fields in parse_packages((folder / "Packages").read_text(encoding="utf-8")):
        deb = folder / fields["Filename"]
        if deb.exists() and hashlib.sha256(deb.read_bytes()).hexdigest() != fields["SHA256"]:
            raise RepoError(f"{deb.name} doesn't match its sum in Packages")


# ----------------------------------------------------------------- publishing (gh)

def gh(*args, capture: bool = True) -> str:
    done = subprocess.run(["gh", *args], capture_output=capture, text=True)
    if done.returncode != 0:
        raise RepoError(f"gh {' '.join(args)}: {done.stderr.strip() if capture else done.returncode}")
    return done.stdout if capture else ""


def published_packages(work: Path) -> str:
    """The Packages published now ('' if there is none yet)."""
    try:
        gh("release", "download", TAG, "--repo", REPO, "--pattern", "Packages", "--dir", str(work), "--clobber")
    except RepoError as e:
        if "no assets" in str(e).lower() or "not found" in str(e).lower() or "no matches" in str(e).lower():
            return ""
        raise
    return (work / "Packages").read_text(encoding="utf-8")


def add(debs: list[Path], key: str = KEY, publish: bool = True, work: Path | None = None,
        public_key: Path = PUBLIC_ASC, gnupghome: str | None = None) -> list[str]:
    """The .deb files DEBS added to the repository (each the newest of its package, or ignored if an equal or
    newer one is there); the index written, signed, checked and, if PUBLISH, uploaded with the new files, and the
    replaced ones deleted. Returns the names of the .deb files published."""
    for d in debs:
        if not d.is_file():
            raise RepoError(f"{d}: no such file")
    owned = work is None
    work = Path(tempfile.mkdtemp(prefix="apt-repo-")) if work is None else work
    try:
        existing = parse_packages(published_packages(work)) if publish else (
            parse_packages((work / "Packages").read_text(encoding="utf-8")) if (work / "Packages").exists() else [])
        new = []
        for d in debs:
            target = work / d.name
            if target.resolve() != d.resolve():
                shutil.copy2(d, target)
            new.append(entry(target))
        stanzas, gone = merge(existing, new)
        added = [f["Filename"] for f in stanzas if f["Filename"] in {n["Filename"] for n in new}]
        write_index(work, stanzas, key, gnupghome)
        verify(work, public_key)
        if publish:
            files = [str(work / n) for n in added] + [str(work / n) for n in INDEX] + [str(PUBLIC_ASC), str(PUBLIC_GPG)]
            gh("release", "upload", TAG, *files, "--repo", REPO, "--clobber", capture=False)
            for name in gone:
                gh("release", "delete-asset", TAG, name, "--repo", REPO, "--yes")
        return added
    finally:
        if owned:
            shutil.rmtree(work, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="apt_repo.py", description="The APT repository of nivaca's programs.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add", help="add .deb files (the newest of each package stays), sign and publish")
    p.add_argument("debs", nargs="+", type=Path)
    p.add_argument("--key", default=KEY, help="the signing key (default: the key of the releases)")
    p.add_argument("--dry-run", action="store_true", help="write and check the index here, in --work; publish nothing")
    p.add_argument("--work", type=Path, help="the folder to work in (with --dry-run: kept, to look at)")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            work = args.work or Path(tempfile.mkdtemp(prefix="apt-repo-"))
            work.mkdir(parents=True, exist_ok=True)
            added = add(args.debs, args.key, publish=False, work=work)
            print(f"apt_repo.py: written and checked in {work} (not published): {', '.join(added) or 'nothing new'}")
        else:
            added = add(args.debs, args.key, work=args.work)
            print(f"apt_repo.py: published {', '.join(added) or 'nothing new'} at {URL}")
    except (RepoError, subprocess.CalledProcessError, OSError) as e:
        print(f"apt_repo.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
