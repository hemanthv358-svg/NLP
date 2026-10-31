import json
import logging
import math
import re
import urllib.error
import urllib.request

from backend.app.config import MODEL_NAME, OLLAMA_URL, THINKING_DEBUG
from backend.app.vector_store import sanitize_scraped_text


def model_status():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as response:
            payload = json.load(response)
        models = [model.get("name", "") for model in payload.get("models", [])]
        ready = any(name.split(":")[0] == MODEL_NAME for name in models)
        return {"ready": ready, "model": MODEL_NAME, "installed_models": models}
    except (OSError, ValueError, urllib.error.URLError):
        return {"ready": False, "model": MODEL_NAME, "installed_models": []}


ANALYSIS_TERMS = re.compile(
    r"\b(analy[sz]e|analysis|chart|compare|comparison|distribution|graph|plot|statistics|trend|visuali[sz]e)\b",
    re.I,
)
LOGGER = logging.getLogger(__name__)
THINKING_CONFIG = {
    "off": (512, "Do not produce a thought block. Give only the direct answer in one short paragraph, maximum three sentences."),
    "low": (768, "Reason briefly inside <thought> tags. Give a compact answer with the essential facts only, using at most five sentences or bullets."),
    "medium": (1536, "Reason carefully inside <thought> tags. Explain the answer with key evidence, useful context, citations, and one clear limitation when relevant."),
    "high": (3072, "Reason thoroughly inside <thought> tags and cross-check the retrieved sources. Give a structured, detailed answer that separates confirmed facts, interpretation, evidence gaps, and practical conclusions. Do not pad or repeat."),
}


def _retrieved_context(documents):
    return "\n\n".join(
        f"[{index}] {sanitize_scraped_text(document['title'])}\n<untrusted_web_content>"
        f"{sanitize_scraped_text(document['content'])}</untrusted_web_content>\nSource: {document['source_url']}"
        for index, document in enumerate(documents, start=1)
    ) or "No matching knowledge was found."


def stream_model_answer(question, documents, history, style, source_site, stop_event=None, thinking="medium"):
    if stop_event and stop_event.is_set():
        return
    context = _retrieved_context(documents)
    styles = {
        "concise": "Answer in two to five clear sentences or short bullets.",
        "detailed": "Give a structured answer with useful headings and bullets.",
        "student": "Use simple, warm, student-friendly language and practical guidance.",
    }
    token_budget, thinking_instruction = THINKING_CONFIG[thinking]
    system_prompt = (
        f"You are a reliable research assistant answering questions about {source_site}. "
        "Use only the supplied retrieved knowledge. Never invent fees, dates, rankings, placement "
        "figures, contacts, claims, or policies. If evidence is incomplete, say so and recommend "
        "checking the source website. Cite evidence with [1], [2], and so on. Answer the question "
        "directly in plain text, avoid repeated conclusions or headings, and do not add generic "
        "recommendations unless asked. "
        + styles.get(style, styles["concise"])
        + " " + thinking_instruction
    )
    safe_history = [
        {"role": item.get("role"), "content": str(item.get("content", ""))[:2_000]}
        for item in history[-6:]
        if item.get("role") in {"user", "assistant"}
    ]
    payload = {
        "model": MODEL_NAME,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            *safe_history,
            {"role": "user", "content": f"Retrieved knowledge:\n{context}\n\nQuestion: {question}"},
        ],
        "options": {"temperature": 0.1 if thinking == "high" else 0.15, "num_ctx": 8192, "num_predict": token_budget},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        output_parts = []
        with urllib.request.urlopen(request, timeout=180) as response:
            for line in response:
                if stop_event and stop_event.is_set():
                    break
                if not line.strip():
                    continue
                event = json.loads(line)
                content = event.get("message", {}).get("content", "")
                if content:
                    output_parts.append(content)
                if event.get("done"):
                    break
        output = "".join(output_parts)
        thoughts = re.findall(r"<thought>(.*?)</thought>", output, flags=re.I | re.S)
        if THINKING_DEBUG and thoughts:
            LOGGER.debug("Filtered model thought: %s", "\n".join(thoughts))
        clean_answer = re.sub(r"<thought>.*?</thought>", "", output, flags=re.I | re.S).strip()
        clean_answer = re.sub(r"</?thought>", "", clean_answer, flags=re.I).strip()
        if clean_answer:
            yield clean_answer
    except urllib.error.URLError as error:
        yield f"Unable to reach the local Ollama model: {error.reason}"
    except TimeoutError:
        yield "The local model timed out. Please try again."


def analyze_documents(question, documents, style, source_site, stop_event=None, thinking="medium"):
    if not ANALYSIS_TERMS.search(question) or not documents:
        return None
    context = _retrieved_context(documents)
    token_budget, thinking_instruction = THINKING_CONFIG[thinking]
    payload = {
        "model": MODEL_NAME,
        "stream": True,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    f"Analyze only the supplied evidence from {source_site}. Return one JSON object with "
                    '"answer" and "chart". The answer must be concise and cite sources as [1]. Chart must '
                    'be null unless the evidence contains numeric values useful for comparison. Otherwise chart '
                    'must be {"type":"bar" or "line","title":"...","x_label":"...","y_label":"...",'
                    '"labels":[...],"values":[...]}. Never invent or estimate values. Use at most 12 values.'
                    f" Response depth rule: {thinking_instruction}"
                ),
            },
            {
                "role": "user",
                "content": f"Evidence:\n{context}\n\nAnalysis request: {question}\nStyle: {style}",
            },
        ],
        "options": {"temperature": 0.05, "num_ctx": 8192, "num_predict": token_budget},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    parts = []
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            for line in response:
                if stop_event and stop_event.is_set():
                    return None
                if not line.strip():
                    continue
                event = json.loads(line)
                parts.append(event.get("message", {}).get("content", ""))
                if event.get("done"):
                    break
        result = json.loads("".join(parts))
    except (json.JSONDecodeError, OSError, TimeoutError, urllib.error.URLError):
        return None
    answer = str(result.get("answer", "")).strip()
    if not answer:
        return None
    chart = result.get("chart")
    if not isinstance(chart, dict) or chart.get("type") not in {"bar", "line"}:
        chart = None
    else:
        labels = chart.get("labels")
        values = chart.get("values")
        if (
            not isinstance(labels, list)
            or not isinstance(values, list)
            or len(labels) != len(values)
            or not 1 < len(values) <= 12
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values)
        ):
            chart = None
        else:
            chart = {
                "type": chart["type"],
                "title": str(chart.get("title", "Data analysis"))[:120],
                "x_label": str(chart.get("x_label", ""))[:60],
                "y_label": str(chart.get("y_label", ""))[:60],
                "labels": [str(label)[:50] for label in labels],
                "values": values,
            }
    return {"answer": answer, "chart": chart}
