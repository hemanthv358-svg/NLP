import re
import sys
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM


DATA_CANDIDATES = [
    # Path("datasets/jssstu_qa_dataset.json"),
    Path("datasets/jssstu_qa.json"),
]


MODEL_NAME = "google/flan-t5-base"
LOCAL_MODEL_DIR = Path("saved_models/t5_qa")
TOP_K = 3
MIN_ANSWER_LEN = 3



def load_dataset():
    for path in DATA_CANDIDATES:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError("Dataset JSON must contain a list of records.")

            return data, path

    raise FileNotFoundError("Dataset JSON not found.")



def normalize(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text



def keyword_overlap_score(query, text):
    q_words = set(normalize(query).split())
    t_words = set(normalize(text).split())
    return len(q_words & t_words)


def retrieve_top_rows(data, user_question, top_k=TOP_K):
    scored = []

    for item in data:
        q = item.get("question", "")
        a = item.get("answer", "")
        topic = item.get("topic", "")

        score_q = keyword_overlap_score(user_question, q)
        score_a = keyword_overlap_score(user_question, a)
        score_t = keyword_overlap_score(user_question, topic)

        total_score = (2 * score_q) + score_a + score_t
        scored.append((total_score, score_q, score_a, score_t, item))

    scored.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
    return [item for _, _, _, _, item in scored[:top_k]]



def build_context(rows):
    context_parts = []

    for row in rows:
        topic = row.get("topic", "general")
        question = row.get("question", "")
        answer = row.get("answer", "")
        context_parts.append(f"Topic: {topic}. Question: {question} Answer: {answer}")

    return " ".join(context_parts)



def load_or_download_model():
    if LOCAL_MODEL_DIR.exists():
        print(f"Loading model from local folder: {LOCAL_MODEL_DIR}")
        tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(LOCAL_MODEL_DIR)
    else:
        print(f"Downloading model from Hugging Face: {MODEL_NAME}")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

        LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        tokenizer.save_pretrained(LOCAL_MODEL_DIR)
        model.save_pretrained(LOCAL_MODEL_DIR)
        print(f"Model saved locally at: {LOCAL_MODEL_DIR}")

    model.eval()
    return tokenizer, model



def answer_question(tokenizer, model, question, context):
    prompt = (
        "Answer the question using only the given context.\n"
        f"Context: {context}\n"
        f"Question: {question}\n"
        "Answer:"
    )

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=512
    )

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=64,
            do_sample=False,
            num_beams=4,
            early_stopping=True
        )

    answer = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
    return answer



def get_fallback_answer(top_rows):
    if not top_rows:
        return "No relevant information found in the dataset."

    answers = []
    for row in top_rows:
        ans = str(row.get("answer", "")).strip()
        if ans and ans not in answers:
            answers.append(ans)

    if not answers:
        return "No relevant information found in the dataset."

    if len(answers) == 1:
        return answers[0]

    return " | ".join(answers[:3])


def should_use_fallback(answer):
    if not answer:
        return True

    cleaned = answer.strip().lower()

    bad_outputs = {
        "",
        "answer:",
        "unknown",
        "not sure",
        "i don't know",
        "no answer"
    }

    if cleaned in bad_outputs:
        return True

    if len(cleaned) < MIN_ANSWER_LEN:
        return True

    return False



def print_top_rows(top_rows):
    print("\nTOP MATCHED DATASET ROWS:")
    for i, row in enumerate(top_rows, start=1):
        print(f"\n[{i}] Topic: {row.get('topic', 'general')}")
        print(f"Question: {row.get('question', '')}")
        print(f"Answer  : {row.get('answer', '')}")



def main():
    print("JSSSTU QA System - T5 (Generative Model with Fallback + Local Save)")

    try:
        data, dataset_path = load_dataset()
        print(f"Dataset loaded from: {dataset_path}")
        print(f"Total records: {len(data)}")
    except Exception as e:
        print(f"Dataset loading error: {e}")
        sys.exit(1)

    try:
        tokenizer, model = load_or_download_model()
        print("Model loaded successfully.\n")
    except Exception as e:
        print(f"Model loading error: {e}")
        sys.exit(1)

    while True:
        user_question = input("Enter your question (type 'exit' to quit): ").strip()

        if user_question.lower() in ["exit", "quit"]:
            print("Exiting program.")
            break

        if not user_question:
            print("Please enter a valid question.\n")
            continue

        top_rows = retrieve_top_rows(data, user_question, top_k=TOP_K)
        context = build_context(top_rows)

        model_answer = answer_question(tokenizer, model, user_question, context)

        print("\n" + "=" * 80)
        print("QUESTION:", user_question)

        if should_use_fallback(model_answer):
            fallback_answer = get_fallback_answer(top_rows)
            print("ANSWER  :", fallback_answer)
            print("SOURCE  : Dataset fallback used")
        else:
            print("ANSWER  :", model_answer)
            print("SOURCE  : T5 model")

        print_top_rows(top_rows)
        print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()