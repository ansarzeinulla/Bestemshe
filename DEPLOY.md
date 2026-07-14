# Deployment Guide

Two targets, two strategies (GitHub's free LFS tier is only 1GB, so the 8.3GB
tablebase goes to Hugging Face only):

| Target | Contents |
|---|---|
| GitHub | Code only — `layers/` stays gitignored |
| HF Space | Code + Dockerfile + `layers/compressed` (8.3GB, LFS) |

## 1. GitHub (code-only)

```bash
git add -A
git commit -m "Restructure: promote New/ to root, add Tablebase Explorer"
git remote add origin git@github.com:<you>/Bestemshe.git
git push -u origin audit-optimize-harden   # or merge to main first
```

Nothing under `layers/` is committed (see `.gitignore`), so no LFS needed on GitHub.

## 2. Hugging Face Space

The Space `ansarzeinulla/Bestemshe-God-Algorithm` already exists as a free **Gradio SDK**
space (Docker Spaces require a PRO subscription; Gradio ones are free). The C++ CLI is
compiled at app startup — `packages.txt` installs g++/make/libzstd-dev via apt, and
`app.py` builds `./query` on first launch. Do NOT upload the Dockerfile or a README
with `sdk: docker` — that converts the Space to Docker and triggers a 402.

```bash
pip install -U "huggingface_hub[cli]"
hf auth login    # the CLI is `hf` (huggingface-cli is deprecated)
```

### Option A (recommended): HfApi.upload_folder

NOTE: `hf upload` fails with `402 Payment Required` on free-tier Gradio Spaces because
the CLI always hits the `repos/create` endpoint first (even for existing repos). The
Python API commits directly to the existing repo and works. Run from the repo root:

```python
from huggingface_hub import HfApi
api = HfApi()

# Code
api.upload_folder(
    repo_id="ansarzeinulla/Bestemshe-God-Algorithm", repo_type="space",
    folder_path=".",
    allow_patterns=["app.py", "requirements.txt", "packages.txt", "query.cpp",
                    "Oracle.h", "StateIndex.h", "BestemsheCore.h", ".gitattributes", "README.md"],
)

# Tablebase (8.3GB, LFS automatically)
api.upload_folder(
    repo_id="ansarzeinulla/Bestemshe-God-Algorithm", repo_type="space",
    folder_path="layers/compressed", path_in_repo="layers/compressed",
)
```

This uploads code + `layers/compressed` (large files automatically stored as LFS
server-side). Resumable if the 8.3GB transfer drops. The Space then builds the
Dockerfile and serves the Gradio app on port 7860.

### Option B: pure git-lfs push

```bash
git clone https://huggingface.co/spaces/ansarzeinulla/Bestemshe-God-Algorithm hf-space
cd hf-space
git lfs install
cp -R ../{app.py,requirements.txt,Dockerfile,README.md,.gitattributes,query.cpp,Oracle.h,StateIndex.h,BestemsheCore.h} .
mkdir -p layers && cp -R ../layers/compressed layers/compressed
# IMPORTANT: do NOT copy the repo .gitignore into the HF clone — it ignores layers/.
git add -A
git commit -m "Bestemshe Tablebase Explorer"
git push   # pushes 8.3GB via LFS; expect it to take a while
```

`.gitattributes` already routes `layers/compressed/*.bin` through LFS.

## Notes

- The Docker image COPYs the tablebase into the image; first build takes a while
  but queries never load more than one 4MB block into RAM.
- To test the container locally: `docker build -t bestemshe . && docker run -p 7860:7860 bestemshe`.
