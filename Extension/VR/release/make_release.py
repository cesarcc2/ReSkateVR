#!/usr/bin/env python3
"""Stage a ReSkate VR release beside the upstream release it is built on.

The launcher of a VR build updates from this fork's releases (DINGOSDK_RELEASE_REPO), so each
release needs the launcher.json the launcher reads. It is upstream's, with two changes:
- `launcher` and `runtime` pin this build's ReSkateLauncher.exe and ReSkate.dll (release assets);
- every other `asset:` download (the dedicated servers) points at upstream's release, since
  VR players use the same servers. The game build and DepotDownloader stay as upstream pins them.

Writes into OUT: ReSkate.dll, ReSkateLauncher.exe, launcher.json and ReSkateVR-<version>.zip
(the first install: those three, openxr_loader.dll, upstream's licences and the OpenXR licence).
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ASSET = "asset:"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pinned(path, version):
    return {"version": version, "url": ASSET + path.name, "sha256": sha256(path), "size": path.stat().st_size}


def launcher_config(upstream, upstream_repo, upstream_tag, launcher, runtime, version):
    config = json.loads(Path(upstream).read_text(encoding="utf-8"))
    if config.get("schema") != 1:
        raise ValueError(f"Upstream launcher.json schema {config.get('schema')} is not supported")
    base = f"https://github.com/{upstream_repo}/releases/download/{upstream_tag}/"
    for key, section in config.items():
        if isinstance(section, dict) and str(section.get("url", "")).startswith(ASSET):
            section["url"] = base + section["url"][len(ASSET):]
    config["launcher"] = pinned(launcher, version)
    config["runtime"] = pinned(runtime, version)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True, help="x.y.z, as stamped into the binaries")
    parser.add_argument("--binaries", type=Path, required=True, help="folder with ReSkate.dll and ReSkateLauncher.exe")
    parser.add_argument("--openxr-loader", type=Path, required=True, help="x64 openxr_loader.dll")
    parser.add_argument("--openxr-license", type=Path, required=True)
    parser.add_argument("--upstream-config", type=Path, required=True, help="upstream release's launcher.json")
    parser.add_argument("--upstream-zip", type=Path, required=True, help="upstream release's ReSkate-<version>.zip (licences)")
    parser.add_argument("--upstream-repo", required=True, help="owner/repo")
    parser.add_argument("--upstream-tag", required=True)
    parser.add_argument("--readme", type=Path, required=True, help="text put in the zip as README-VR.txt")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    out = args.out
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    runtime, launcher = out / "ReSkate.dll", out / "ReSkateLauncher.exe"
    shutil.copy2(args.binaries / "ReSkate.dll", runtime)
    shutil.copy2(args.binaries / "ReSkateLauncher.exe", launcher)
    config = launcher_config(args.upstream_config, args.upstream_repo, args.upstream_tag, launcher, runtime, args.version)
    text = json.dumps(config, indent=4) + "\n"
    (out / "launcher.json").write_text(text, encoding="utf-8", newline="\n")

    with tempfile.TemporaryDirectory(prefix="reskate-vr-") as temporary:
        stage = Path(temporary) / "stage"
        stage.mkdir()
        with zipfile.ZipFile(args.upstream_zip) as upstream:
            for entry in upstream.infolist():
                name = entry.filename
                if name == "LICENSE.txt" or (name.startswith("licenses/") and not entry.is_dir()):
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(upstream.read(entry))
        (stage / "licenses").mkdir(exist_ok=True)
        shutil.copy2(args.openxr_license, stage / "licenses" / "OpenXR-LICENSE.txt")
        for path in (runtime, launcher, out / "launcher.json"):
            shutil.copy2(path, stage / path.name)
        shutil.copy2(args.openxr_loader, stage / "openxr_loader.dll")
        shutil.copy2(args.readme, stage / "README-VR.txt")
        packer = Path(__file__).resolve().parents[3] / "contrib" / "package_release_zip.py"
        subprocess.run([sys.executable, "-I", str(packer), str(stage), str(out / f"ReSkateVR-{args.version}.zip")], check=True)
    for path in sorted(out.iterdir()):
        print(f"{sha256(path)[:12]}  {path.stat().st_size:>10}  {path.name}")


if __name__ == "__main__":
    main()
