import os
import sys
import warnings

# Suppress all HF and tokenizer warnings
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Suppress Python warnings
warnings.filterwarnings("ignore")

# Suppress logging from huggingface_hub and sentence_transformers
import logging
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

import sqlite3
import numpy as np
import random
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB

DB_PATH = 'foodshare.db'

def load_seed_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT food_name, food_type FROM seed_foods")
    data = cur.fetchall()
    conn.close()
    return [(name, ftype) for name, ftype in data]

# ------------------------------------------------------------
# Sentence-BERT (Layer 3) evaluation
# ------------------------------------------------------------
def generate_paraphrase(food_name):
    """Generate a simple descriptive query from a food name."""
    name_lower = food_name.lower()
    if 'cake' in name_lower:
        return f"sweet {food_name} dessert"
    elif 'bread' in name_lower:
        return f"fresh {food_name} loaf"
    elif 'fruit' in name_lower or name_lower in ['apple','banana','mango','orange','peach','pear','plum','cherry','kiwi','lemon','lime','grapefruit','avocado','pomegranate']:
        return f"ripe {food_name} fruit"
    elif 'salad' in name_lower or 'vegetable' in name_lower or name_lower in ['broccoli','carrot','spinach','cucumber','lettuce','celery','asparagus','cauliflower','zucchini','eggplant','cabbage','peas','corn','radish','beetroot','onion','garlic']:
        return f"fresh {food_name} vegetable"
    elif any(kw in name_lower for kw in ['pizza','burger','pasta','rice','soup','curry','stew','omelette','sandwich','salmon','steak']):
        return f"hearty {food_name} meal"
    else:
        return f"tasty {food_name}"

def evaluate_sentence_bert(seed_names, num_queries=200):
    """Randomly sample food names, generate queries, compute Recall@K and MRR."""
    model = SentenceTransformer('all-MiniLM-L6-v2')
    seed_emb = model.encode(seed_names)
    
    sample_size = min(num_queries, len(seed_names))
    sampled_names = random.sample(seed_names, sample_size)
    queries = [generate_paraphrase(name) for name in sampled_names]
    
    recall_1 = 0
    recall_3 = 0
    recall_5 = 0
    sum_rr = 0
    
    for i, query in enumerate(queries):
        q_emb = model.encode([query])[0]
        sim = np.dot(seed_emb, q_emb) / (np.linalg.norm(seed_emb, axis=1) * np.linalg.norm(q_emb))
        ranked_indices = np.argsort(sim)[::-1]
        ranked_names = [seed_names[idx] for idx in ranked_indices]
        correct = sampled_names[i]
        try:
            rank = [idx for idx, name in enumerate(ranked_names) if name.lower() == correct.lower()][0] + 1
        except IndexError:
            rank = None
        if rank is not None:
            sum_rr += 1.0 / rank
            if rank == 1:
                recall_1 += 1
            if rank <= 3:
                recall_3 += 1
            if rank <= 5:
                recall_5 += 1
    
    n = len(queries)
    return recall_1/n, recall_3/n, recall_5/n, sum_rr/n

# ------------------------------------------------------------
# Naive Bayes (Layer 4) evaluation
# ------------------------------------------------------------
def evaluate_naive_bayes(names, types):
    X_train, X_test, y_train, y_test = train_test_split(
        names, types, test_size=0.2, random_state=42, stratify=types
    )
    vec = CountVectorizer()
    X_train_vec = vec.fit_transform(X_train)
    X_test_vec = vec.transform(X_test)
    clf = MultinomialNB()
    clf.fit(X_train_vec, y_train)
    y_pred = clf.predict(X_test_vec)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average='weighted')
    labels = ['cake', 'bread', 'fruit', 'meal', 'vegetable']
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    return acc, f1, cm, labels

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    data = load_seed_data()
    names = [item[0] for item in data]
    types = [item[1] for item in data]
    
    # 1. Sentence-BERT (Layer 3)
    print("===== Layer 3 (Sentence‑BERT) =====")
    r1, r3, r5, mrr = evaluate_sentence_bert(names, num_queries=200)
    print(f"Recall@1: {r1:.4f}")
    print(f"Recall@3: {r3:.4f}")
    print(f"Recall@5: {r5:.4f}")
    print(f"MRR: {mrr:.4f}")
    
    # 2. Naive Bayes (Layer 4)
    print("\n===== Layer 4 (Naive Bayes) =====")
    acc, f1, cm, labels = evaluate_naive_bayes(names, types)
    print(f"Accuracy: {acc:.4f}")
    print(f"Weighted F1-score: {f1:.4f}")
    print("Confusion Matrix (rows=true, cols=predicted):")
    print("       " + "  ".join(labels))
    for i, row in enumerate(cm):
        print(f"{labels[i]:8} " + "  ".join([str(v) for v in row]))

if __name__ == '__main__':
    main()