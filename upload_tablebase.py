"""Chunked tablebase uploader for the HF Space.

Sorts layers/compressed by file size (largest first). Files >= BIG_THRESHOLD are
committed one per commit; smaller files are batched into groups of <= GROUP_BYTES.
Files already present on the Space are skipped, so the script is fully resumable —
just rerun it after any failure.
"""

import os
import sys

from huggingface_hub import HfApi, CommitOperationAdd

REPO = "ansarzeinulla/bestemshe-tablebase"
REPO_TYPE = "dataset"
LOCAL_DIR = "layers/compressed"
BIG_THRESHOLD = 100 * 1024 * 1024   # 100MB: upload individually
GROUP_BYTES = 500 * 1024 * 1024     # small files: <=500MB per commit

api = HfApi()

existing = set(api.list_repo_files(REPO, repo_type=REPO_TYPE))

files = []
for name in os.listdir(LOCAL_DIR):
    path = os.path.join(LOCAL_DIR, name)
    if not os.path.isfile(path):
        continue
    repo_path = f"{LOCAL_DIR}/{name}"
    if repo_path in existing:
        continue
    files.append((os.path.getsize(path), path, repo_path))

files.sort(reverse=True)  # largest first
total = sum(f[0] for f in files)
print(f"[plan] {len(files)} files to upload, {total / 1e9:.2f} GB "
      f"({len(existing)} repo files already present)", flush=True)

# Build commit groups: big files alone, small files batched.
groups, batch, batch_bytes = [], [], 0
for size, path, repo_path in files:
    if size >= BIG_THRESHOLD:
        groups.append([(size, path, repo_path)])
    elif batch_bytes + size > GROUP_BYTES and batch:
        groups.append(batch)
        batch, batch_bytes = [(size, path, repo_path)], size
    else:
        batch.append((size, path, repo_path))
        batch_bytes += size
if batch:
    groups.append(batch)

done_bytes = 0
for i, group in enumerate(groups, 1):
    ops = [CommitOperationAdd(path_in_repo=rp, path_or_fileobj=p) for _, p, rp in group]
    gb = sum(s for s, _, _ in group) / 1e9
    label = group[0][2] if len(group) == 1 else f"{len(group)} files"
    print(f"[{i}/{len(groups)}] committing {label} ({gb:.2f} GB)...", flush=True)
    api.create_commit(
        repo_id=REPO, repo_type=REPO_TYPE, operations=ops,
        commit_message=f"Tablebase upload {i}/{len(groups)}: {label}",
    )
    done_bytes += sum(s for s, _, _ in group)
    print(f"    done — {done_bytes / 1e9:.2f}/{total / 1e9:.2f} GB total", flush=True)

print("[SUCCESS] tablebase fully uploaded.")
