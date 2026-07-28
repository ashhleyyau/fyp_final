import sqlite3
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split

DB_PATH = 'foodshare.db'

# Load seed data from database
def load_seed_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT food_name, food_type FROM seed_foods")
    data = cursor.fetchall()
    conn.close()
    return [(name, ftype) for name, ftype in data]

# Evaluate precision and recall at k
def evaluate_precision_recall_at_k(train_names, train_types, test_names, test_types, k=5):
    if not train_names or not test_names:
        return 0.0, 0.0

    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(1,2))
    train_vectors = vectorizer.fit_transform(train_names)

    precision_list = []
    recall_list = []

    for query, true_type in zip(test_names, test_types):
        relevant_indices = [i for i, t in enumerate(train_types) if t == true_type]
        if not relevant_indices:
            continue

        query_vec = vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, train_vectors)[0]
        top_k_indices = np.argsort(similarities)[::-1][:k]

        retrieved_relevant = sum(1 for idx in top_k_indices if train_types[idx] == true_type)
        precision = retrieved_relevant / k
        precision_list.append(precision)

        total_relevant = len(relevant_indices)
        recall = retrieved_relevant / total_relevant if total_relevant > 0 else 0
        recall_list.append(recall)

    avg_precision = np.mean(precision_list) if precision_list else 0.0
    avg_recall = np.mean(recall_list) if recall_list else 0.0
    return avg_precision, avg_recall

# Main evaluation
def main():
    print("Loading seed data from database...")
    data = load_seed_data()
    if not data:
        print("No seed data found. Please run app.py first to initialize database.")
        return

    names = [item[0] for item in data]
    types = [item[1] for item in data]

    train_names, test_names, train_types, test_types = train_test_split(
        names, types, test_size=0.2, random_state=42, stratify=types
    )

    print(f"Training set size: {len(train_names)}")
    print(f"Test set size: {len(test_names)}")
    print("\nEvaluating TF-IDF semantic expansion (Layer 3)...\n")

    for k in [1, 3, 5, 10]:
        prec, rec = evaluate_precision_recall_at_k(
            train_names, train_types, test_names, test_types, k=k
        )
        print(f"k={k}: Precision@{k} = {prec:.4f}, Recall@{k} = {rec:.4f}")

if __name__ == '__main__':
    main()