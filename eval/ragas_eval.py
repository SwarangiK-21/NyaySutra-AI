"""RAGAS step 2: score saved answers with RAGAS (Retrieval-Augmented Generation Assessment).

    pip install -r requirements-eval.txt        # once (evaluation only; not needed by the app or its Docker image)
    python eval/ragas_eval.py eval/runs/<timestamp>/answers.jsonl

Metrics (reference-free unless a lawyer-written reference answer is present):
  * faithfulness                  — are the answer's claims supported by the passages it was given?
  * answer_relevancy              — does the answer address the question?
  * context_precision (no ref.)   — were the retrieved passages useful for this answer?
  * context_recall                — only for questions with a reference answer: did retrieval find what it needs?
The judge is the app's own model client (nyaya/llm.py: OpenAI gpt-6-luna by default, identity numbers masked,
unsupported settings handled); embeddings are the app's local model (nothing extra leaves the machine).
Each answer costs a few judge calls (roughly 10–15): run small sets. Writes ragas_scores.json and ragas_report.md
next to the answers file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from langchain_core.outputs import Generation, LLMResult
    from ragas import EvaluationDataset, RunConfig, evaluate
    from ragas.embeddings.base import BaseRagasEmbeddings
    from ragas.llms.base import BaseRagasLLM
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference, LLMContextRecall, ResponseRelevancy
except ImportError as exc:  # evaluation extras not installed
    raise SystemExit(f"RAGAS is not installed ({exc}). Run: pip install -r requirements-eval.txt") from exc

from nyaya import config, embeddings, llm  # noqa: E402


class NyayaJudge(BaseRagasLLM):
    """RAGAS judge backed by the app's LLM client (same provider, key, masking and error handling as the app)."""

    def __init__(self, model: str):
        super().__init__()
        self.model = model

    def _complete(self, prompt) -> str:
        text = prompt.to_string() if hasattr(prompt, "to_string") else str(prompt)
        return llm.chat([{"role": "user", "content": text}], model=self.model, temperature=0.0)

    def generate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None) -> LLMResult:
        return LLMResult(generations=[[Generation(text=self._complete(prompt)) for _ in range(max(1, n))]])

    async def agenerate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None) -> LLMResult:
        texts = [await asyncio.to_thread(self._complete, prompt) for _ in range(max(1, n))]
        return LLMResult(generations=[[Generation(text=x) for x in texts]])

    def is_finished(self, response: LLMResult) -> bool:
        return True


class NyayaEmbeddings(BaseRagasEmbeddings):
    """The app's local embedding model (fastembed / ONNX): runs on this machine."""

    def embed_query(self, text: str) -> list[float]:
        return [float(x) for x in embeddings.embed_query(text)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in embeddings.embed_passages(list(texts))]

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)


def _num(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 3)


def main() -> int:
    ap = argparse.ArgumentParser(description="Score saved answers with RAGAS.")
    ap.add_argument("answers", help="answers.jsonl written by eval/collect_answers.py")
    ap.add_argument("--model", default=config.FAST_LLM_MODEL, help="judge model (default: the app's fast model)")
    args = ap.parse_args()
    path = Path(args.answers)
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    usable = [r for r in rows if r["response"] and r["retrieved_contexts"] and not r.get("error")]
    skipped = [r["id"] for r in rows if r not in usable]
    if not usable:
        print("Nothing to score (every answer had an error or no passages).")
        return 2

    has_ref = all(r.get("reference") for r in usable)
    metrics = [Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithoutReference()]
    if has_ref:
        metrics.append(LLMContextRecall())
    dataset = EvaluationDataset.from_list([
        {"user_input": r["user_input"], "response": r["response"], "retrieved_contexts": r["retrieved_contexts"],
         **({"reference": r["reference"]} if r.get("reference") else {})} for r in usable])
    print(f"Scoring {len(usable)} answer(s) with {', '.join(m.name for m in metrics)} · judge {args.model}"
          + (f" · skipped {skipped}" if skipped else ""))
    t0 = time.time()
    result = evaluate(dataset=dataset, metrics=metrics, llm=NyayaJudge(args.model), embeddings=NyayaEmbeddings(),
                      run_config=RunConfig(max_workers=2, timeout=240, max_retries=2), show_progress=True)
    table = result.to_pandas()
    names = [m.name for m in metrics]
    per = []
    for r, (_, s) in zip(usable, table.iterrows()):
        per.append({"id": r["id"], "category": r["category"], "lang": r["lang"], "verified_by_app": r.get("verified"),
                    **{n: _num(s.get(n)) for n in names}})
    means = {n: _num(table[n].mean(skipna=True)) for n in names}
    out = {"answers_file": str(path), "judge": args.model, "metrics": names, "mean": means, "items": per,
           "skipped": skipped, "seconds": round(time.time() - t0, 1)}
    (path.parent / "ragas_scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")

    lines = ["# RAGAS evaluation", "", f"- Answers: `{path.name}` ({len(usable)} scored"
             + (f", skipped {', '.join(skipped)}" if skipped else "") + ")",
             f"- Answer model: {usable[0].get('model')} · judge: {args.model}", "",
             "| Metric | Mean (0–1, higher is better) |", "|---|---|"]
    lines += [f"| {n} | {means[n] if means[n] is not None else '—'} |" for n in names]
    lines += ["", "| Id | Category | " + " | ".join(names) + " | App citation check |",
              "|---|---|" + "---|" * len(names) + "---|"]
    lines += [f"| {p['id']} | {p['category']} | " + " | ".join("—" if p[n] is None else str(p[n]) for n in names)
              + f" | {'verified' if p['verified_by_app'] else 'issues' if p['verified_by_app'] is False else '—'} |"
              for p in per]
    lines += ["", "Synthetic questions only. Scores from an AI judge are indicative, not a lawyer's review."]
    (path.parent / "ragas_report.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines[5:5 + 2 + len(names)]))
    print(f"Report: {path.parent / 'ragas_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
