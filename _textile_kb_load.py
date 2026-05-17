"""Filter chunks for textile/budget keywords, generate QA, index. Logs progress."""
import sys, time, os
# Resolve project root from this file's location so the script works on any clone path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from knowledge_base.pipeline import _read_jsonl, _append_jsonl, CHUNKS_PATH, QA_PATH
from knowledge_base.qa_generator import generate_qa_for_chunk
from knowledge_base.vector_store import KBVectorStore

# PG-textile: keywords for textile + budget impact filtering
KEYS = ('textile','garment','apparel','cotton','handloom','PM Mitra','MITRA',
        'MSME','budget','jute','silk','fabric','spinning','yarn','khadi',
        'PLI scheme')

def main():
    t0 = time.time()
    chunks = _read_jsonl(CHUNKS_PATH)
    hits = [c for c in chunks if any(k.lower() in c['text'].lower() for k in KEYS)]
    print(f"[{time.time()-t0:.1f}s] matched {len(hits)} of {len(chunks)} chunks", flush=True)

    existing_qa = {r['qa_id'] for r in _read_jsonl(QA_PATH)}
    new_qa, batch = [], []
    for i, ch in enumerate(hits):
        pairs = [p for p in generate_qa_for_chunk(ch) if p['qa_id'] not in existing_qa]
        batch.extend(pairs); new_qa.extend(pairs)
        # Flush every 5 chunks to disk so we don't lose work
        if (i+1) % 5 == 0:
            _append_jsonl(QA_PATH, batch); batch.clear()
            print(f"[{time.time()-t0:.1f}s] {i+1}/{len(hits)} chunks → {len(new_qa)} QA pairs", flush=True)
    if batch:
        _append_jsonl(QA_PATH, batch)

    print(f"[{time.time()-t0:.1f}s] indexing into Chroma...", flush=True)
    store = KBVectorStore()
    nc = store.upsert_chunks(hits)
    nq = store.upsert_qa(new_qa)
    print(f"[{time.time()-t0:.1f}s] DONE: chunks={nc}, qa={nq}, totals={store.stats()}", flush=True)

if __name__ == "__main__":
    main()
