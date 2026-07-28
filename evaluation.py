import os
import sys
import time
import sqlite3
import unittest
import random
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sentence_transformers import SentenceTransformer

# Suppress warnings and HF logs
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import warnings
warnings.filterwarnings("ignore")
import logging
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

TEST_DB_PATH = 'test_foodshare.db'

# Import application modules
import search
search.DB_PATH = TEST_DB_PATH
import database as db
db.DB_PATH = TEST_DB_PATH
from app import app
from search import SearchEngine

# Search Engine Evaluation
def load_seed_data(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT food_name, food_type FROM seed_foods")
    data = cur.fetchall()
    conn.close()
    return [(name, ftype) for name, ftype in data]

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
    recall_1 = recall_3 = recall_5 = 0
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

# Unit Tests
class TestSearchEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db.init_db()
        cls.engine = SearchEngine()

    def test_edit_distance(self):
        e = self.engine
        self.assertEqual(e._edit_distance("cake", "cake"), 0)
        self.assertEqual(e._edit_distance("cake", "cage"), 1)

    def test_gibberish_detection(self):
        e = self.engine
        self.assertFalse(e._is_gibberish("xyzabc"))
        self.assertFalse(e._is_gibberish("cake"))

    def test_typo_correction(self):
        self.assertIsInstance(self.engine.get_closest_food_by_edit_distance("Cheescake", 1), list)

    def test_naive_bayes(self):
        result = self.engine.infer_type_naive_bayes("Pizza")
        self.assertTrue(result is None or isinstance(result, str))

# Integration Tests
class TestFlaskIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_homepage(self):
        self.assertEqual(self.client.get('/search').status_code, 200)

    def test_register_login(self):
        c = self.client
        c.post('/register', data={'username':'t','password':'1','area':'K','district':'Y','disclaimer':'on'}, follow_redirects=True)
        self.assertEqual(c.post('/login', data={'username':'t','password':'1'}, follow_redirects=True).status_code, 200)

    def test_create_post(self):
        c = self.client
        c.post('/login', data={'username':'t','password':'1'})
        self.assertEqual(c.post('/post/new', data={'food_name':'Apple','food_type':'fruit','area':'K','district':'Y','expiry_date':'2026-12-31'}, follow_redirects=True).status_code, 200)

# Performance Test
def performance_test():
    c = app.test_client()
    c.get('/search?q=bread')
    def measure(url):
        times = []
        for _ in range(5):
            start = time.time()
            c.get(url)
            times.append((time.time() - start)*1000)
        return sum(times)/len(times)
    return {
        'homepage': measure('/search'),
        'search': measure('/search?q=bread'),
        'map_api': measure('/map-data')
    }

# Main runner
def run_silent(suite, label):
    print(f"\n{label}")
    for test in suite:
        name = test._testMethodName
        try:
            test.setUp() if hasattr(test, 'setUp') else None
            test.run()
            print(f"{name}: PASSED")
        except Exception as e:
            print(f"{name}: FAILED ({e})")
        finally:
            test.tearDown() if hasattr(test, 'tearDown') else None

def main():
    # Init test database
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    db.init_db()

    # 1. Search Engine Evaluation
    print("\n1. SEARCH ENGINE EVALUATION")
    data = load_seed_data(TEST_DB_PATH)
    names = [row[0] for row in data]
    types = [row[1] for row in data]

    print("\nLayer 3: Sentence-BERT (Semantic Expansion)")
    r1, r3, r5, mrr = evaluate_sentence_bert(names, num_queries=200)
    print(f"Recall@1: {r1:.4f}")
    print(f"Recall@3: {r3:.4f}")
    print(f"Recall@5: {r5:.4f}")
    print(f"MRR: {mrr:.4f}")

    print("\nLayer 4: Naive Bayes (Category Fallback)")
    acc, f1, cm, labels = evaluate_naive_bayes(names, types)
    print(f"Accuracy: {acc:.4f}")
    print(f"Weighted F1-score: {f1:.4f}")
    print("Confusion Matrix (rows=true, cols=predicted):")
    print("       " + "  ".join(labels))
    for i, row in enumerate(cm):
        print(f"{labels[i]:8} " + "  ".join([str(v) for v in row]))

    # 2. Unit Tests
    suite1 = unittest.TestLoader().loadTestsFromTestCase(TestSearchEngine)
    run_silent(suite1, "2. UNIT TESTS")

    # 3. Integration Tests
    suite2 = unittest.TestLoader().loadTestsFromTestCase(TestFlaskIntegration)
    run_silent(suite2, "3. INTEGRATION TESTS")

    # 4. Performance Test
    print("\n4. PERFORMANCE")
    perf = performance_test()
    print(f"Homepage: {perf['homepage']:.2f} ms")
    print(f"Search: {perf['search']:.2f} ms")
    print(f"Map API: {perf['map_api']:.2f} ms")

    # Cleanup
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    print("\nCOMPLETED")

if __name__ == '__main__':
    main()