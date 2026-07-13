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

Create the Space once: https://huggingface.co/new-space — SDK: **Docker**, public,
free CPU basic (16GB RAM, 50GB disk — both sufficient).

```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli login
```

### Option A (recommended): HTTP upload — resumable, no git-lfs juggling

```bash
huggingface-cli upload <you>/bestemshe-explorer . . \
  --repo-type space \
  --exclude ".git/*" "*.o" "bestemshe" "query" "build/*" "*.so" "docs/*"
```

This uploads code + `layers/compressed` (large files automatically stored as LFS
server-side). Resumable if the 8.3GB transfer drops. The Space then builds the
Dockerfile and serves the Gradio app on port 7860.

### Option B: pure git-lfs push

```bash
git clone https://huggingface.co/spaces/<you>/bestemshe-explorer hf-space
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
