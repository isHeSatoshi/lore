"""Download public BIRD data, discover its layout, and record portable paths."""

import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

import httpx

from lore.config import ROOT, settings

HF = "https://huggingface.co/datasets/birdsql/bird_mini_dev/resolve/main"


def download(url, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size:
        return
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(4):
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                size = 0
                with part.open("wb") as out:
                    for block in response.iter_bytes(1024 * 1024):
                        out.write(block)
                        size += len(block)
                        if size // (64 * 1024 * 1024) != (size - len(block)) // (64 * 1024 * 1024):
                            print(f"{dest.name}: {size} bytes", flush=True)
                length = response.headers.get("content-length")
                if length and int(length) != size:
                    raise OSError("Incomplete download")
            part.replace(dest)
            print(f"Downloaded {dest.name}: {size} bytes", flush=True)
            return
        except (httpx.HTTPError, OSError):
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def extract(archive, target):
    marker = target / (archive.name + ".extracted")
    if marker.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            path = (target / member.filename).resolve()
            if not path.is_relative_to(target.resolve()):
                raise ValueError("Archive contains an unsafe path")
        z.extractall(target)
    marker.touch()
    print(f"Extracted {archive.name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minidev-dbs", action="store_true")
    args = parser.parse_args()
    bird = settings.bird_dir
    mini = bird / "minidev"
    files = {
        "test.jsonl": HF + "/data/mini_dev_sqlite.jsonl",
        "published.jsonl": HF + "/baseline_inference/mini_dev_sqlite.jsonl",
        "prompt_template.txt": HF + "/baseline_inference/prompt_template.txt",
        "sqlite.json": HF + "/baseline_inference/schemas/sqlite.json",
    }
    for name, url in files.items():
        download(url, mini / name)
    archive = bird / "dev.zip"
    download("https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip", archive)
    extract(archive, bird / "dev")
    # Discover nested archives, rather than assuming a release-specific directory.
    for nested in sorted((bird / "dev").rglob("*.zip")):
        extract(nested, nested.parent / nested.stem)
    db_root = bird / "dev"
    if args.minidev_dbs:
        archive = bird / "minidev.zip"
        download("https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip", archive)
        db_root = bird / "mini_databases"
        extract(archive, db_root)
        for nested in sorted(db_root.rglob("*.zip")):
            extract(nested, nested.parent / nested.stem)
    devs = sorted((bird / "dev").rglob("dev.json"))
    if not devs:
        raise FileNotFoundError("Cannot find dev.json in the downloaded archive")
    dbs = {p.stem: p for p in sorted(db_root.rglob("*.sqlite")) if "__MACOSX" not in p.parts}
    test_ids = {
        json.loads(line)["db_id"] for line in (mini / "test.jsonl").read_text().splitlines()
    }
    if not test_ids <= dbs.keys():
        raise FileNotFoundError(f"Missing SQLite databases: {sorted(test_ids - dbs.keys())}")
    paths = {
        "dev": str(devs[0].relative_to(bird)),
        "databases": {k: str(dbs[k].relative_to(bird)) for k in sorted(test_ids)},
        "descriptions": {},
    }
    for key in sorted(test_ids):
        candidates = list(dbs[key].parent.rglob("database_description"))
        if not candidates:
            candidates = [
                p for p in (bird / "dev").rglob("database_description") if p.parent.name == key
            ]
        if candidates:
            paths["descriptions"][key] = str(candidates[0].relative_to(bird))
    (bird / "paths.json").write_text(json.dumps(paths, indent=2) + "\n")
    manifest = {}
    for name, url in files.items():
        content = (mini / name).read_bytes()
        manifest[name] = {
            "url": url,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    target = ROOT / "results" / "data"
    target.mkdir(parents=True, exist_ok=True)
    (target / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Recorded {len(test_ids)} databases in data/bird/paths.json", flush=True)


if __name__ == "__main__":
    main()
