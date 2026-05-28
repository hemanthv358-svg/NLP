import re
import sys
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForQuestionAnswering

# --------------------------------------------------
# DATASET PATHS
# --------------------------------------------------
DATA_CANDIDATES = [
    # Path("datasets/jssstu_qa_dataset.json"),
    Path("datasets/jssstu_qa.json"),
]

MODEL_NAME = "deepset/roberta-base-squad2"
TOP_K = 3
MIN_SCORE = 0.25


# --------------------------------------------------
# LOAD DATASET
# --------------------------------------------------
def load_dataset():
    for path in DATA_CANDIDATES:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError("Dataset JSON must contain a list of records.")

            return data, path

    raise FileNotFoundError("Dataset JSON not found.")


# --------------------------------------------------
# TEXT CLEANING
# --------------------------------------------------
def normalize(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


# --------------------------------------------------
# SIMPLE RETRIEVAL
# --------------------------------------------------
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


# --------------------------------------------------
# BUILD CONTEXT
# --------------------------------------------------
def build_context(rows):
    context_parts = []

    for row in rows:
        topic = row.get("topic", "general")
        question = row.get("question", "")
        answer = row.get("answer", "")
        context_parts.append(f"Topic: {topic}. Question: {question} Answer: {answer}")

    return " ".join(context_parts)


# --------------------------------------------------
# DIRECT MODEL ANSWERING
# --------------------------------------------------
def answer_question(tokenizer, model, question, context):
    inputs = tokenizer(
        question,
        context,
        return_tensors="pt",
        truncation="only_second",
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**inputs)

    start_idx = torch.argmax(outputs.start_logits, dim=1).item()
    end_idx = torch.argmax(outputs.end_logits, dim=1).item()

    if end_idx < start_idx:
        end_idx = start_idx

    answer_tokens = inputs["input_ids"][0][start_idx:end_idx + 1]
    answer = tokenizer.decode(answer_tokens, skip_special_tokens=True).strip()

    start_prob = torch.max(torch.softmax(outputs.start_logits, dim=1)).item()
    end_prob = torch.max(torch.softmax(outputs.end_logits, dim=1)).item()
    score = float(start_prob * end_prob)

    return answer, score


# --------------------------------------------------
# FALLBACK LOGIC
# --------------------------------------------------
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


# --------------------------------------------------
# DISPLAY RESULTS
# --------------------------------------------------
def print_top_rows(top_rows):
    print("\nTOP MATCHED DATASET ROWS:")
    for i, row in enumerate(top_rows, start=1):
        print(f"\n[{i}] Topic: {row.get('topic', 'general')}")
        print(f"Question: {row.get('question', '')}")
        print(f"Answer  : {row.get('answer', '')}")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    print("JSSSTU QA System - RoBERTa (Direct Model with Fallback)")

    try:
        data, dataset_path = load_dataset()
        print(f"Dataset loaded from: {dataset_path}")
        print(f"Total records: {len(data)}")
    except Exception as e:
        print(f"Dataset loading error: {e}")
        sys.exit(1)

    try:
        print(f"Loading model: {MODEL_NAME}")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
        model.eval()
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

        model_answer, score = answer_question(tokenizer, model, user_question, context)

        use_fallback = False
        if not model_answer.strip():
            use_fallback = True
        elif len(model_answer.strip()) < 2:
            use_fallback = True
        elif score < MIN_SCORE:
            use_fallback = True

        print("\n" + "=" * 80)
        print("QUESTION:", user_question)

        if use_fallback:
            fallback_answer = get_fallback_answer(top_rows)
            print("ANSWER  :", fallback_answer)
            print("SOURCE  : Dataset fallback used")
            print("SCORE   :", f"{score:.4f}")
        else:
            print("ANSWER  :", model_answer)
            print("SOURCE  : RoBERTa model")
            print("SCORE   :", f"{score:.4f}")

        print_top_rows(top_rows)
        print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()