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

1. Run the **Configurations** cell.
   Tokens are optional — public HF models and public CivitAI resources work
   with both fields blank; only gated/private HF models need one.
2. Run the **Start** cell.
   Offline package URL is hardcoded, nothing to fill in.
3. For gated HF models, also click "Agree/Access repository" once on HF's site.

## How it works

**One prebuilt package**
Webui + its pinned sub-repos + a chosen set of extensions + the maintainer's
tuned `config.json` are pre-built into a single offline package
(`build_package.py`). Every run just extracts that package — from a local
file next to the notebook or from HuggingFace — instead of cloning and
configuring everything from scratch.

**Resource management**
Models, LoRAs, VAEs, embeddings, and extensions are managed as a list of
resource links per category, each independently enable/disable-able, with
an option to cache a resource into persistent storage so it survives across
instances instead of re-downloading every time.

**Carried-over state**
Tokens (HF/CivitAI) and the resource list are saved to `links.json`, so a
new instance picks up the same setup automatically.
