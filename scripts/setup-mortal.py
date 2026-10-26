"""Configure the verified community checkpoint after its Docker runtime is built."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "mortal-298k"


def main():
    manifest = json.loads((MODEL_DIR / "provenance.json").read_text(encoding="utf-8"))
    checkpoint = MODEL_DIR / manifest["checkpoint"]
    with checkpoint.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("Checkpoint differs from the verified download manifest")
    subprocess.run(
        ["docker", "image", "inspect", "xmahjong/mortal:local"], check=True, stdout=subprocess.DEVNULL
    )
    config_path = ROOT / "config.local.json"
    config = json.loads(
        (config_path if config_path.exists() else ROOT / "config.example.json").read_text(
            encoding="utf-8-sig"
        )
    )
    if config.get("mortal", {}).get("command"):
        backup = ROOT / "data" / "config.before-mortal-298k.json"
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            backup.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    config["mortal"] = {
        "command": [
            "docker",
            "run",
            "--rm",
            "-i",
            "--mount",
            f"type=bind,source={MODEL_DIR.as_posix()},target=/mnt,readonly",
            "xmahjong/mortal:local",
            "{actor}",
        ],
        "version": f"{manifest['model_id']}@{manifest['revision'][:12]} / Mortal v4",
        "weight_sha256": digest,
        "timeout": 180,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Configured community Mortal checkpoint. Restart the XMahjong service to apply.")


if __name__ == "__main__":
    main()
