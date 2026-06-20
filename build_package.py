#!/usr/bin/env python3
"""
Builds the offline "sdw package" consumed by auto_launcher.ipynb's PACKAGE_URL setting,
and uploads it to a HuggingFace repo.

Bundles AUTOMATIC1111/stable-diffusion-webui (dev branch) + its 5 pinned sub-repos
(repositories/...) + a chosen set of extensions (extensions/...) into one archive,
with .git directories kept intact so that:
  - webui's own git_clone() sees each sub-repo already at its expected commit and
    skips re-cloning it (see modules/launch_utils.py: git_clone() returns immediately
    when `git rev-parse HEAD` already matches the expected commit hash).
  - the notebook's existing "Update stable diffusion first" / "Update all extensions
    on launch" checkboxes can still `git pull` everything to latest on top of this seed.

Default models/VAEs are not bundled here - auto_launcher.ipynb's own Params.links
class attribute is the single source of truth for what a fresh links.json gets
seeded with, independent of whatever this package contains.

Run manually, occasionally, by whoever maintains the package - not part of the
end-user notebook flow. Needs a write-scoped HuggingFace token.

Usage:
    python build_package.py --hf-repo <user>/<repo> --hf-token hf_xxx
    python build_package.py --output sdw_package.tar.xz --no-upload   # build only
"""
import argparse
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

WEBUI_REPO_URL = "https://github.com/AUTOMATIC1111/stable-diffusion-webui"
WEBUI_BRANCH = "dev"

# Maintainer's tuned config.json, packed alongside (not inside) the webui tree so
# auto_launcher.ipynb's extract_offline_package() can pull it out to /notebooks/config.json
# on first extraction - see EXTRA_DIR there.
CONFIG_FILE = Path(__file__).parent / "config.json"
EXTRA_DIR = "_package_extra"

# repositories/<dir> -> (ENV var name for the repo URL, ENV var name for the commit hash)
# as found in webui's own modules/launch_utils.py - parsed out of that file below rather
# than hardcoded, so the package stays self-consistent with whatever webui commit it's
# built from even after upstream bumps these pins.
SUB_REPOS = {
    "stable-diffusion-webui-assets": ("ASSETS_REPO", "ASSETS_COMMIT_HASH"),
    "stable-diffusion-stability-ai": ("STABLE_DIFFUSION_REPO", "STABLE_DIFFUSION_COMMIT_HASH"),
    "generative-models": ("STABLE_DIFFUSION_XL_REPO", "STABLE_DIFFUSION_XL_COMMIT_HASH"),
    "k-diffusion": ("K_DIFFUSION_REPO", "K_DIFFUSION_COMMIT_HASH"),
    "BLIP": ("BLIP_REPO", "BLIP_COMMIT_HASH"),
}

# Edit this list to change which extensions get bundled into the package.
EXTENSIONS = {
    "sd-model-downloader": "https://github.com/Iyashinouta/sd-model-downloader",
    "sd-webui-agent-scheduler": "https://github.com/ArtVentureX/sd-webui-agent-scheduler",
    "sd-webui-infinite-image-browsing": "https://github.com/zanllp/sd-webui-infinite-image-browsing",
    "sd-webui-controlnet": "https://github.com/Mikubill/sd-webui-controlnet",
}

# Edit this to change the default models/VAEs auto_launcher.ipynb queues for download on
# a fresh package seed. Not downloaded here - these URLs go through the *notebook's*
# own (already-fixed) aria2/requests download pipeline at first-run time, same as any
# URL the user adds manually. Keys here match Params' "links" categories.
def run(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}" + (f"  (cwd={cwd})" if cwd else ""))
    subprocess.run(cmd, cwd=cwd, check=True)


def git_clone_at(url: str, dst: Path, commit: str | None = None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    run(["git", "clone", "--quiet", url, str(dst)])
    if commit:
        run(["git", "-C", str(dst), "checkout", "--quiet", commit])


def parse_env_default(text: str, env_name: str) -> str:
    # Matches: os.environ.get('ENV_NAME', "default value") - either quote style on the
    # default - as used throughout webui's modules/launch_utils.py.
    pattern = rf"os\.environ\.get\(\s*['\"]{re.escape(env_name)}['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"Couldn't find a default for {env_name} in launch_utils.py - webui's source may have changed format.")
    return m.group(1)


def build(scratch_dir: Path) -> Path:
    sdw_dir = scratch_dir / "sdw"
    if sdw_dir.exists():
        shutil.rmtree(sdw_dir)

    print(f"== Cloning webui ({WEBUI_BRANCH}) ==")
    run(["git", "clone", "--quiet", "-b", WEBUI_BRANCH, WEBUI_REPO_URL, str(sdw_dir)])

    launch_utils = (sdw_dir / "modules" / "launch_utils.py").read_text(encoding="utf-8")

    print("== Cloning pinned sub-repos ==")
    repositories_dir = sdw_dir / "repositories"
    repositories_dir.mkdir(exist_ok=True)
    for dir_name, (repo_env, commit_env) in SUB_REPOS.items():
        url = parse_env_default(launch_utils, repo_env)
        commit = parse_env_default(launch_utils, commit_env)
        print(f"-- {dir_name}: {url} @ {commit}")
        git_clone_at(url, repositories_dir / dir_name, commit)

    print("== Cloning extensions ==")
    extensions_dir = sdw_dir / "extensions"
    extensions_dir.mkdir(exist_ok=True)
    for dir_name, url in EXTENSIONS.items():
        print(f"-- {dir_name}: {url}")
        git_clone_at(url, extensions_dir / dir_name)

    return sdw_dir


def pack_package(sdw_dir: Path, output: Path) -> Path:
    # tar.xz (LZMA), not zip - stdlib only, no extra dependency, and noticeably
    # smaller than zip's DEFLATE for a payload that's mostly small git-repo text
    # files, with less per-file overhead than zip across many small files.
    print(f"== Packing into {output} ==")
    if output.exists():
        output.unlink()
    with tarfile.open(output, "w:xz") as tf:
        tf.add(sdw_dir, arcname=".")
        if CONFIG_FILE.exists():
            tf.add(CONFIG_FILE, arcname=f"{EXTRA_DIR}/{CONFIG_FILE.name}")
            print(f"-- bundled {CONFIG_FILE.name} under {EXTRA_DIR}/")
        else:
            print(f"-- {CONFIG_FILE.name} not found next to build_package.py, skipping bundle")
    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Package built: {output} ({size_mb:.1f} MB)")
    return output


def upload(output: Path, hf_repo: str, hf_token: str, repo_type: str) -> None:
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("huggingface_hub is required to upload - install it with: pip install huggingface_hub", file=sys.stderr)
        raise

    print(f"== Uploading to https://huggingface.co/{repo_type}s/{hf_repo} ==")
    api = HfApi(token=hf_token)
    api.create_repo(repo_id=hf_repo, repo_type=repo_type, exist_ok=True)
    api.upload_file(
        path_or_fileobj=str(output),
        path_in_repo=output.name,
        repo_id=hf_repo,
        repo_type=repo_type,
    )
    print(f"Uploaded. Download URL: https://huggingface.co/{repo_type}s/{hf_repo}/resolve/main/{output.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scratch-dir", default="./_package_build", help="Scratch directory for the clones (default: ./_package_build)")
    parser.add_argument("--output", default="sdw_package.tar.xz", help="Output archive path (default: sdw_package.tar.xz)")
    parser.add_argument("--hf-repo", help="Target HuggingFace repo id, e.g. myuser/sdwebui-package")
    parser.add_argument("--hf-token", help="Write-scoped HuggingFace token (or set HF_WRITE_TOKEN env var)")
    parser.add_argument("--repo-type", default="dataset", choices=["dataset", "model"], help="HF repo type to upload to (default: dataset)")
    parser.add_argument("--no-upload", action="store_true", help="Build the archive only, skip the HF upload")
    args = parser.parse_args()

    scratch_dir = Path(args.scratch_dir).resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    output = Path(args.output).resolve()

    sdw_dir = build(scratch_dir)
    pack_package(sdw_dir, output)
    shutil.rmtree(scratch_dir, ignore_errors=True)

    if args.no_upload:
        print("--no-upload set, skipping HF upload.")
        return

    import os
    hf_token = args.hf_token or os.environ.get("HF_WRITE_TOKEN")
    if not args.hf_repo or not hf_token:
        print("Provide --hf-repo and --hf-token (or HF_WRITE_TOKEN) to upload, or pass --no-upload to just build the zip.", file=sys.stderr)
        sys.exit(1)

    upload(output, args.hf_repo, hf_token, args.repo_type)


if __name__ == "__main__":
    main()
