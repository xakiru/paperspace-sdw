# Paperspace SD-WebUI Notebook — Notes

Runs AUTOMATIC1111's Stable Diffusion WebUI on Paperspace Gradient.

## Files
| File | What it is |
|---|---|
| `auto_launcher.ipynb` | The notebook — Configurations + Start cells |
| `build_package.py` | Builds/uploads the offline `sdw` package (run manually by the maintainer) |
| `build_package.ipynb` | UI wrapper for `build_package.py` |
| `links.json` / `config.json` | Live runtime state (tokens, enabled resources, webui settings) |

## How to use
1. Run **Configurations** cell. Tokens are optional — public HF models and
   public CivitAI resources work with both fields blank; only gated/private
   HF models need one.
2. Run **Start** cell. Offline package URL is hardcoded, nothing to fill in.
3. For gated HF models, still click "Agree/Access repository" once on HF's site.

## How it works
**Auth**
- HF token / CivitAI token: `Text` fields in Configurations, persisted in
  `links.json`, fall back to `HF_TOKEN`/`CIVITAI_TOKEN` env vars.
- HF uses an `Authorization: Bearer` header. CivitAI's token is used only for
  the metadata API call, never the actual download URL (CivitAI's CDN does a
  TLS/client fingerprint check aria2 can't pass).
- CivitAI downloads go through Python `requests` with browser
  `User-Agent`/`Referer` headers (`civitai_requests_download()`), not aria2.
  Everything else (HF, Google Drive, extensions, generic URLs) uses aria2.
- Gated/login-required CivitAI resources are not supported — only public
  CivitAI resources work.

**Downloads**
- aria2 defaults to single-connection (`-x1 -s1`) since HF/CivitAI hand out
  freshly-signed, single-use URLs that 403 on segmented downloads. "Fast
  parallel downloads" (off by default) opts into `-x16 -s16`.
- `looks_like_failed_download()` flags 0-byte/HTML/JSON-error files and
  deletes them. Failed categories log and continue instead of aborting.

**Startup**
- Start cell seeds `sdw/` from a "Local package file" next to the notebook
  if it exists (default: `sdw_package.tar.xz`), otherwise downloads from the
  hardcoded `OFFLINE_PACKAGE_URL` (see `build_package.py`); falls back to
  `git clone` if both fail.
- WebUI launches right after extensions sync, before models/vaes/loras
  download — those continue in a background thread.
- Launch goes through `subprocess.Popen` (not the `!` shell magic) so the
  Start cell can rewrite Gradio's `Running on local URL: http://0.0.0.0:6006`
  line into the real public Paperspace URL
  (`https://tensorboard-{PAPERSPACE_FQDN}`) while still streaming all other
  output live.
- "Custom config" (on by default) points `--ui-settings-file` at `config.json`
  in the notebook root (persistent storage). The offline package bundles the
  maintainer's tuned `config.json` (see `build_package.py`'s `EXTRA_DIR`); on
  first extraction it's copied to the notebook root automatically, so a fresh
  instance starts with that tuning instead of webui's bare defaults - existing
  `config.json` is never overwritten. Any later edits via the Settings tab
  persist across instance restarts. "Update stable diffusion first" does
  `git pull` in place.
- Generated images always save to the Outputs path (no toggle) - redirected
  via `sed` on `config.json`'s `outdir_*` keys.
