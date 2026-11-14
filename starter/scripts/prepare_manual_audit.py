"""Prepare the manual audit: samples, blind worksheets, and an automatic metadata check.

Run from starter/ (needs the Docker DB up):  python -m scripts.prepare_manual_audit

Writes results/manual/:
  coherence_sheet.md / coherence_labels.csv   10 source positions x {A, B}; C reuses B's chunks
  grounding_sheet.md / grounding_labels.csv   5 test questions x top-3; identical B/C top-3 shown once
  metadata_check.csv / metadata_summary.json  5 test questions x top-3 x {A, B, C}, checked vs manifest + DB
  key.json                                    id -> strategy (kept out of the worksheets to blind the labeller)
You fill the *_labels.csv score/reason columns by reading the *_sheet.md files.
"""
import csv
import json
import os
import random
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from src.run import CORPUS, DOCUMENT_ID, INDEXES, ROOT, STARTER, load_chapters

SEED = 20261114  # fixed before looking at any label
POSITION_PAGES = range(5, 96, 10)  # chapters 5, 15, ..., 95: spread over the whole novel
OUT = ROOT / "results" / "manual"

load_dotenv(STARTER / ".env")
OUT.mkdir(parents=True, exist_ok=True)
manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
units = {u["unit_id"]: u for u in manifest["units"]}
pages = {p.page: p for p in load_chapters(CORPUS, DOCUMENT_ID, manifest["source_path_or_url"])}
rng = random.Random(SEED)


def quote(text: str) -> str:
    return "\n".join("> " + line for line in text.split("\n"))


def write_labels(name: str, ids: list[str]) -> None:
    with (OUT / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "score", "reason"])
        w.writerows([i, "", ""] for i in ids)


# ---- 1. coherence: the chunk covering the midpoint of 10 fixed chapters, for A and B ----
rows = []
for page_no in POSITION_PAGES:
    page = pages[page_no]
    pos = len(page.text) // 2
    for index in ("A", "B"):
        chunk = next(c for c in INDEXES[index](page)
                     if c.metadata["char_start"] <= pos < c.metadata["char_end"])
        rows.append({"index": index, "page": page_no, "pos": pos, "chunk": chunk})
rng.shuffle(rows)
key, lines = {}, ["# Phiếu chấm coherence\n",
                  "Thang: **0** = bị cắt giữa ý / thiếu chủ thể nên không hiểu; **1** = hiểu một phần, "
                  "thiếu ngữ cảnh; **2** = tự hiểu được và giữ trọn ý. Điền `score` và `reason` vào "
                  "`coherence_labels.csv`. Thứ tự đã xáo, chưa ghi chiến lược.\n"]
for n, r in enumerate(rows, start=1):
    cid = f"c{n:02d}"
    key[cid] = {"index": r["index"], "chunk_id": r["chunk"].chunk_id, "page": r["page"], "pos": r["pos"]}
    u = pages[r["page"]].metadata
    lines += [f"## {cid}  ·  {u['book']}, Chapter {u['chapter']} ({u['chapter_title']})\n", quote(r["chunk"].text), ""]
(OUT / "coherence_sheet.md").write_text("\n".join(lines), encoding="utf-8")
write_labels("coherence_labels.csv", list(key))
coherence_key = key

# ---- 2. grounding: top-3 of the 5 test questions; label once when B and C retrieved the same ----
questions = {q["id"]: q for q in json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))}
traces = [json.loads(l) for l in (ROOT / "results" / "traces_test.jsonl").read_text(encoding="utf-8").splitlines()]
groups: dict[tuple, dict] = {}
for t in traces:
    g = groups.setdefault((t["id"], tuple(h["chunk_id"] for h in t["hits"])), {"trace": t, "strategies": []})
    g["strategies"].append(t["strategy"])
items = list(groups.values())
rng.shuffle(items)
key, lines = {}, ["# Phiếu chấm grounding\n",
                  "Chỉ đánh giá **bằng chứng truy xuất**, không phải câu trả lời của LLM. Thang: **0** = không có "
                  "bằng chứng; **1** = có nhưng thiếu điều kiện/ngữ cảnh cần thiết; **2** = đủ để trả lời và truy "
                  "nguồn. Xét **cả top-3 cùng nhau**. Điền vào `grounding_labels.csv`.\n"]
for n, g in enumerate(items, start=1):
    gid, t = f"g{n:02d}", g["trace"]
    q = questions[t["id"]]
    key[gid] = {"question": t["id"], "strategies": g["strategies"], "chunk_ids": [h["chunk_id"] for h in t["hits"]]}
    lines += [f"## {gid}\n", f"**Câu hỏi:** {q['question']}  ", f"**Đáp án mong đợi:** {q['expected_answer']}  ",
              f"**Evidence gold:** “{q['evidence_quote']}”  ",
              f"**Filter cung cấp:** {q['filter'] or 'không'}\n"]
    for h in t["hits"]:
        lines += [f"**Top-{h['rank']}** · {h['book']}, chương {h['page']} ({h['unit_id']})", quote(h["text"]), ""]
(OUT / "grounding_sheet.md").write_text("\n".join(lines), encoding="utf-8")
write_labels("grounding_labels.csv", list(key))
grounding_key = key

(OUT / "key.json").write_text(json.dumps({"seed": SEED, "coherence": coherence_key,
                                          "grounding": grounding_key}, indent=2), encoding="utf-8")

# ---- 3. metadata: each top-3 record of the 5 test questions vs manifest, DB row and chapter text ----
checks = []
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
    for t in traces:
        for h in t["hits"]:
            row = conn.execute("SELECT * FROM chunks WHERE strategy=%s AND chunk_id=%s",
                               (t["index"], h["chunk_id"])).fetchone()
            problems = []
            if row is None:
                problems.append("chunk not in DB")
            else:
                for field in ("document_id", "source", "page", "book", "part"):
                    if row[field] in (None, ""):
                        problems.append(f"{field} missing")
                u = units.get(row["metadata"].get("unit_id"))
                if u is None:
                    problems.append("unit_id not in manifest")
                else:
                    expected = {"document_id": manifest["source_id"], "source": manifest["source_path_or_url"],
                                "page": u["page"], "book": u["book"], "part": u["part"]}
                    problems += [f"{k}={row[k]!r} != manifest {v!r}" for k, v in expected.items() if row[k] != v]
                    if row["text"] not in pages[u["page"]].text:
                        problems.append("chunk text not found in claimed chapter")
                    if row["text"] != h["text"]:
                        problems.append("trace text differs from DB")
            checks.append({"strategy": t["strategy"], "question": t["id"], "rank": h["rank"],
                           "chunk_id": h["chunk_id"], "ok": not problems, "problems": "; ".join(problems)})
with (OUT / "metadata_check.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(checks[0]))
    w.writeheader()
    w.writerows(checks)
summary = {s: {"ok": sum(c["ok"] for c in checks if c["strategy"] == s),
               "total": sum(c["strategy"] == s for c in checks)} for s in "ABC"}
(OUT / "metadata_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

print(f"coherence: {len(coherence_key)} chunks to label (C reuses B)")
print(f"grounding: {len(grounding_key)} cases to label "
      f"({sum(len(v['strategies']) for v in grounding_key.values())} strategy x question results)")
print("metadata (automatic):", summary, "| failures:", [c for c in checks if not c["ok"]])
