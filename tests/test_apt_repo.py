"""Las pruebas del repositorio APT (tools/apt_repo.py): las versiones ordenadas como las ordena dpkg, los .deb
leídos (gzip, xz, zstd), el índice escrito, firmado con una clave de usar y tirar y comprobado con solo la
pública, y una versión nueva que reemplaza a la anterior. Nada se publica."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import apt_repo  # noqa: E402


@pytest.mark.parametrize("a, b, expected", [
    ("1.0", "1.0", 0), ("1.0", "1.1", -1), ("1.10", "1.9", 1), ("1.0~rc1", "1.0", -1), ("1.0-1", "1.0-2", -1),
    ("2:1.0", "1:9.9", 1), ("1.15.0-1", "1.14.0-1", 1), ("3.30-1", "3.4-1", 1), ("1.0a", "1.0", 1),
    ("1.0+b1", "1.0", 1), ("0.1.0-1", "0.1.0-1", 0)])
def test_versions(a, b, expected):
    assert apt_repo.compare_versions(a, b) == expected


def make_deb(folder: Path, package: str, version: str, arch: str = "amd64", compression: str = "gz") -> Path:
    """A small .deb: an ar archive with debian-binary, control.tar.* and data.tar.gz."""
    control = (f"Package: {package}\nVersion: {version}\nArchitecture: {arch}\nMaintainer: Nicolas Vaughan "
               f"<nicolasvaughan@proton.me>\nInstalled-Size: 10\nDepends: libc6\nDescription: a test\n"
               f" with a second line\n").encode()

    def tar_of(files: dict[str, bytes], mode: str) -> bytes:
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode=mode) as tar:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return out.getvalue()

    if compression == "zst":
        from compression import zstd

        control_tar, control_name = zstd.compress(tar_of({"./control": control}, "w")), "control.tar.zst"
    elif compression == "xz":
        control_tar, control_name = tar_of({"./control": control}, "w:xz"), "control.tar.xz"
    else:
        control_tar, control_name = tar_of({"./control": control}, "w:gz"), "control.tar.gz"
    members = [("debian-binary", b"2.0\n"), (control_name, control_tar), ("data.tar.gz", tar_of({}, "w:gz"))]
    data = b"!<arch>\n"
    for name, blob in members:
        data += f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(blob):<10}`\n".encode()
        data += blob + (b"\n" if len(blob) % 2 else b"")
    path = folder / f"{package}_{version}_{arch}.deb"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("compression", ["gz", "xz", "zst"])
def test_reading_a_deb(tmp_path, compression):
    deb = make_deb(tmp_path, "py-test", "1.2.3-1", compression=compression)
    fields = apt_repo.entry(deb)
    assert fields["Package"] == "py-test" and fields["Version"] == "1.2.3-1" and fields["Filename"] == deb.name
    assert fields["Description"] == "a test\n with a second line" and len(fields["SHA256"]) == 64


@pytest.fixture
def throwaway_key(tmp_path):
    """A key of its own, in a GnuPG folder of its own (never the author's): its fingerprint, its folder, and its
    public key exported."""
    home = Path(tempfile_dir := str(tmp_path / "gnupg"))
    home.mkdir(mode=0o700)
    run = lambda *a: subprocess.run(["gpg", "--batch", "--homedir", tempfile_dir, *a], check=True,  # noqa: E731
                                    capture_output=True, text=True)
    run("--passphrase", "", "--quick-gen-key", "Test <test@example.org>", "ed25519", "sign", "1d")
    fpr = next(line.split(":")[9] for line in run("--list-keys", "--with-colons").stdout.splitlines()
               if line.startswith("fpr"))
    public = tmp_path / "public.asc"
    public.write_text(run("--export", "--armor", fpr).stdout)
    return fpr, str(home), public


def test_index_signed_and_checked(tmp_path, throwaway_key):
    fpr, home, public = throwaway_key
    work = tmp_path / "repo"
    work.mkdir()
    debs = [make_deb(tmp_path, "py-a", "1.0-1"), make_deb(tmp_path, "py-b", "2.0-1", arch="all")]
    added = apt_repo.add(debs, fpr, publish=False, work=work, public_key=public, gnupghome=home)
    assert added == ["py-a_1.0-1_amd64.deb", "py-b_2.0-1_all.deb"]
    for name in apt_repo.INDEX:
        assert (work / name).is_file(), name
    release = (work / "Release").read_text()
    assert "Architectures: all amd64" in release and "Suite: stable" in release
    assert "BEGIN PGP SIGNED MESSAGE" in (work / "InRelease").read_text()
    # A newer py-a replaces the older; an older one is left out
    newer = make_deb(tmp_path, "py-a", "1.1-1")
    older = make_deb(tmp_path, "py-b", "1.9-1", arch="all")
    assert apt_repo.add([newer, older], fpr, publish=False, work=work, public_key=public,
                        gnupghome=home) == ["py-a_1.1-1_amd64.deb"]
    names = [f["Filename"] for f in apt_repo.parse_packages((work / "Packages").read_text())]
    assert names == ["py-a_1.1-1_amd64.deb", "py-b_2.0-1_all.deb"]


def test_a_changed_file_is_caught(tmp_path, throwaway_key):
    fpr, home, public = throwaway_key
    work = tmp_path / "repo"
    work.mkdir()
    apt_repo.add([make_deb(tmp_path, "py-a", "1.0-1")], fpr, publish=False, work=work, public_key=public,
                 gnupghome=home)
    apt_repo.verify(work, public)
    (work / "Packages").write_text((work / "Packages").read_text() + "\n")  # (changed after signing)
    with pytest.raises(apt_repo.RepoError, match="doesn't match"):
        apt_repo.verify(work, public)
    (work / "Release").write_text((work / "Release").read_text() + "X: y\n")
    with pytest.raises(apt_repo.RepoError, match="signature"):
        apt_repo.verify(work, public)
