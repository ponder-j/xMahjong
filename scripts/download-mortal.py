"""Download a pinned community checkpoint and verify its publisher SHA-256."""

import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REVISION = "dbbea7e3d34f99ec43fc4834ab7f2aaaed70b6ee"
EXPECTED_SHA256 = "bfb3a6c072aa0bfd4171a9cdc77cb6c02ae42cde920843f9e5784394f23447d8"
MODEL_ID = "VoidShine/mortal-298k"
FILENAME = "mortal_298k.pth"
MODEL_DIR = ROOT / "models" / "mortal-298k"


def file_hash(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    target = MODEL_DIR / FILENAME
    base = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}"
    if target.exists() and file_hash(target) == EXPECTED_SHA256:
        print("Checkpoint already present; SHA-256 verified.", flush=True)
    else:
        temporary = target.with_suffix(".pth.part")
        try:
            with httpx.Client(timeout=httpx.Timeout(60, connect=30), follow_redirects=True) as client:
                with client.stream("GET", f"{base}/{FILENAME}") as response:
                    response.raise_for_status()
                    hasher, size, next_notice = hashlib.sha256(), 0, 10 * 1024 * 1024
                    with temporary.open("wb") as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            output.write(chunk)
                            hasher.update(chunk)
                            size += len(chunk)
                            if size >= next_notice:
                                print(f"Downloaded {size / 1024 / 1024:.0f} MiB", flush=True)
                                next_notice += 10 * 1024 * 1024
                if hasher.hexdigest() != EXPECTED_SHA256:
                    raise ValueError("Checkpoint SHA-256 does not match pinned publisher metadata")
                temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for remote, local in [
            ("README.md", "MODEL_CARD.md"),
            ("LICENSE", "LICENSE"),
            ("config.toml", "training-config.toml"),
        ]:
            response = client.get(f"{base}/{remote}")
            response.raise_for_status()
            (MODEL_DIR / local).write_bytes(response.content)
    manifest = {
        "model_id": MODEL_ID,
        "revision": REVISION,
        "checkpoint": FILENAME,
        "sha256": EXPECTED_SHA256,
        "size": target.stat().st_size,
        "license": "AGPL-3.0",
        "source": f"https://huggingface.co/{MODEL_ID}",
        "official_online_model": False,
        "strength": "Not independently evaluated by XMahjong",
    }
    (MODEL_DIR / "provenance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (MODEL_DIR / "config.toml").write_text(
        "[control]\nstate_file = '/mnt/mortal_298k.pth'\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
