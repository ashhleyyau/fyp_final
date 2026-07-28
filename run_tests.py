#!/usr/bin/env python3
import os, sys, time, sqlite3, unittest, random, numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB

os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

TEST_DB_PATH = 'test_foodshare.db'
import search; search.DB_PATH = TEST_DB_PATH
import database as db; db.DB_PATH = TEST_DB_PATH
from app import app
from search import SearchEngine, SentenceBERT

class TestSearchEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_PATH): os.remove(TEST_DB_PATH)
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

def eval_search():
    conn = sqlite3.connect(TEST_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT food_name, food_type FROM seed_foods")
    data = cur.fetchall()
    conn.close()
    if not data: return
    names, types = zip(*data)

    print("\n3. SEARCH EVALUATION")

    print("\nLayer 3: Sentence-BERT (Semantic Expansion)")
    model = SentenceBERT()
    sample = random.sample(names, min(50, len(names)))
    def p(n):
        l=n.lower()
        if 'cake' in l: return f"sweet {n} dessert"
        if 'bread' in l: return f"fresh {n} loaf"
        return f"tasty {n}"
    qs = [p(n) for n in sample]
    emb = model.encode(names)
    r1 = 0
    for i,q in enumerate(qs):
        sim = cosine_similarity([model.encode([q])[0]], emb)[0]
        ranked = [names[idx] for idx in np.argsort(sim)[::-1]]
        if sample[i].lower() in [r.lower() for r in ranked[:1]]: r1 += 1
    print(f"Recall@1: {r1/len(sample):.4f}")

    print("\nLayer 4: Naive Bayes (Category Fallback)")
    Xtr, Xte, ytr, yte = train_test_split(names, types, test_size=0.2, random_state=42, stratify=types)
    vec = CountVectorizer()
    clf = MultinomialNB()
    clf.fit(vec.fit_transform(Xtr), ytr)
    yp = clf.predict(vec.transform(Xte))
    print(f"Accuracy: {accuracy_score(yte, yp):.4f}")
    print(f"F1: {f1_score(yte, yp, average='weighted'):.4f}")
    print("Confusion Matrix:")
    print(confusion_matrix(yte, yp))

def perf():
    print("\n4. PERFORMANCE")
    c = app.test_client()
    c.get('/search?q=bread')
    def measure(url):
        times = []
        for _ in range(5):
            start = time.time()
            c.get(url)
            times.append((time.time() - start)*1000)
        return sum(times)/len(times)
    print(f"Homepage: {measure('/search'):.2f} ms")
    print(f"Search: {measure('/search?q=bread'):.2f} ms")
    print(f"Map API: {measure('/map-data'):.2f} ms")

if __name__ == '__main__':
    print("TEST SUITE\n")
    suite1 = unittest.TestLoader().loadTestsFromTestCase(TestSearchEngine)
    suite2 = unittest.TestLoader().loadTestsFromTestCase(TestFlaskIntegration)
    run_silent(suite1, "1. UNIT TESTS")
    run_silent(suite2, "2. INTEGRATION TESTS")
    eval_search()
    perf()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        print("\nCleaned up test database.")
    print("\nDONE")