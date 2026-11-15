"""Install only the reviewed official standalone CLI, never run its installer."""

import hashlib
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

VERSION = "1.12.1"
SDK_VERSION = "0.5.0"
HASHES = {
    "x64": "ffd1196837f680327258094bc12dc993ff9232036c964bf8354ffb7ed1fdcf00",
    "x64-baseline": "0b066177663e2d792a7fe13c04f2ad8b9e8df20c474d29e7543cadfa887b30f7",
}
BASE_URL = f"https://downloads.factory.ai/factory-cli/releases/{VERSION}/linux"
MAX_BYTES = 512 * 1024 * 1024


def architecture():
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
        raise RuntimeError("Pinned Droid runtime requires Linux x86_64")
    try:
        avx2 = "avx2" in Path("/proc/cpuinfo").read_text().lower().split()
    except OSError:
        avx2 = False
    return "x64" if avx2 else "x64-baseline"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, destination):
    # No auth, shell, installer execution or mutable "latest" endpoint.
    start, size = time.monotonic(), 0
    with urllib.request.urlopen(url, timeout=30) as response, destination.open("xb") as stream:
        if not response.url.startswith("https://downloads.factory.ai/"):
            raise RuntimeError("Unexpected Droid download redirect")
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES or time.monotonic() - start > 180:
                raise RuntimeError("Droid download exceeded its size/time limit")
            stream.write(chunk)


def verify(path, arch, home):
    # Hash BEFORE executing, including when reusing an existing private cache.
    if path.is_symlink() or digest(path) != HASHES[arch]:
        raise RuntimeError("Pinned Droid checksum differs")
    result = subprocess.run(
        [str(path), "--version"],
        cwd=home,
        env={
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "FACTORY_DROID_AUTO_UPDATE_ENABLED": "false",
        },
        capture_output=True,
        timeout=15,
        check=True,
        text=True,
    )
    if result.stdout.strip() != VERSION:
        raise RuntimeError("Pinned Droid version differs")


def provision_droid(state):
    """Return an immutable-version executable under private executable state."""
    arch = architecture()
    parent = Path(state).resolve() / "droid" / VERSION
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = parent / arch
    if target.is_symlink():
        raise RuntimeError("Pinned Droid cache must not be a symlink")
    with tempfile.TemporaryDirectory(prefix=".provision-", dir=parent) as temporary:
        temporary = Path(temporary)
        home = temporary / "home"
        home.mkdir(mode=0o700)
        if target.exists():
            verify(target / "droid", arch, home)
        else:
            staged = temporary / "release"
            staged.mkdir(mode=0o700)
            binary = staged / "droid"
            download(f"{BASE_URL}/{arch}/droid", binary)
            # An unverified download is never executable.
            if digest(binary) != HASHES[arch]:
                raise RuntimeError("Pinned Droid checksum differs")
            binary.chmod(0o500)
            verify(binary, arch, home)
            shutil.copyfile(Path(__file__).with_name("FACTORY_NOTICE.md"), staged / "FACTORY_NOTICE.md")
            (staged / "provenance.txt").write_text(
                f"version={VERSION}\nurl={BASE_URL}/{arch}/droid\nsha256={HASHES[arch]}\n"
            )
            staged.rename(target)
    return target / "droid"
