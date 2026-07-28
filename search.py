import os
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

import sqlite3
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import CountVectorizer
import difflib
import re
from sentence_transformers import SentenceTransformer

DB_PATH = 'foodshare.db'

class SentenceBERT:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)

    def encode(self, texts):
        return self.model.encode(texts)

class NaiveBayesClassifier:
    def __init__(self):
        self.vectorizer = CountVectorizer()
        self.clf = MultinomialNB()
        self.is_trained = False

    def train(self, food_names, food_types):
        X = self.vectorizer.fit_transform(food_names)
        self.clf.fit(X, food_types)
        self.is_trained = True

    def predict(self, food_name):
        if not self.is_trained:
            return None
        X = self.vectorizer.transform([food_name])
        return self.clf.predict(X)[0]

class SearchEngine:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(1,2))
        self.food_names = []
        self.food_vectors = None
        self._load_seed_data()
        self.base_foods = self._build_base_foods()

        self.sbert = SentenceBERT()
        self.nb_classifier = NaiveBayesClassifier()
        self._train_nb()

        self.food_vectors_sbert = None
        if self.food_names:
            self.food_vectors_sbert = self.sbert.encode(self.food_names)
        print("Search engine ready.")

    def _load_seed_data(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT food_name FROM seed_foods")
        self.food_names = [row[0] for row in cursor.fetchall()]
        conn.close()
        self._train_model()

    def _train_model(self):
        if not self.food_names:
            return
        self.food_vectors = self.vectorizer.fit_transform(self.food_names)

    def _train_nb(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT food_name, food_type FROM seed_foods")
        data = cursor.fetchall()
        conn.close()
        if data:
            names, types = zip(*data)
            self.nb_classifier.train(list(names), list(types))

    def _build_base_foods(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT LOWER(food_name) FROM seed_foods")
        db_foods = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT LOWER(food_name) FROM posts")
        post_foods = [row[0] for row in cursor.fetchall()]
        conn.close()
        all_foods = list(set(db_foods + post_foods))
        return all_foods

    def _edit_distance(self, a, b):
        if len(a) < len(b):
            a, b = b, a
        distances = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            new_distances = [i]
            for j, cb in enumerate(b, 1):
                cost = 0 if ca == cb else 1
                new_distances.append(min(
                    distances[j] + 1,
                    new_distances[-1] + 1,
                    distances[j-1] + cost
                ))
            distances = new_distances
        return distances[-1]

    def get_closest_food_by_edit_distance(self, query, top_n=1):
        query_lower = query.lower()
        matches = difflib.get_close_matches(query_lower, self.base_foods, n=top_n, cutoff=0.6)
        return matches

    def get_similar_foods(self, query, top_n=5):
        if not self.food_names:
            return []
        query_lower = query.lower()
        query_vec = self.vectorizer.transform([query_lower])
        similarities = cosine_similarity(query_vec, self.food_vectors)[0]
        top_indices = np.argsort(similarities)[::-1][:top_n]
        return [self.food_names[i] for i in top_indices]

    def get_similar_foods_sbert(self, query, top_n=5, min_similarity=0.3):
        if not self.food_names or self.food_vectors_sbert is None:
            return []
        query_vec = self.sbert.encode([query])
        sims = cosine_similarity(query_vec, self.food_vectors_sbert)[0]
        top_indices = np.argsort(sims)[::-1][:top_n]
        return [self.food_names[i] for i in top_indices if sims[i] > min_similarity]

    def infer_type_naive_bayes(self, query):
        return self.nb_classifier.predict(query)

    def _is_gibberish(self, s):
        if len(s) < 3:
            return False
        if not re.match(r'^[a-z]+$', s):
            return False
        return not any(c in 'aeiou' for c in s)

    def search(self, query, cursor, area=None, district=None, food_type=None):
        base_where = "status = 'available' AND expiry_date >= date('now')"
        params = []
        if area:
            base_where += " AND area = ?"
            params.append(area)
        if district:
            base_where += " AND district = ?"
            params.append(district)
        if food_type:
            base_where += " AND food_type = ?"
            params.append(food_type)

        def run_like_query(keyword):
            cursor.execute(f"""
                SELECT * FROM posts 
                WHERE (food_name LIKE ? OR description LIKE ? OR food_type LIKE ?)
                AND {base_where}
                ORDER BY expiry_date ASC
                LIMIT 100
            """, (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%') + tuple(params))
            results = cursor.fetchall()
            if food_type:
                results = [row for row in results if row['food_type'] == food_type]
            return results

        # Layer 1: Exact match
        results = run_like_query(query)
        if results:
            return results, None

        # Handle spaces (e.g., "cheese cake" -> "cheesecake")
        query_no_space = query.replace(" ", "")
        if query_no_space != query:
            results = run_like_query(query_no_space)
            if results:
                return results, None

        # Layer 2: Typo correction
        suggestion = None
        closest = self.get_closest_food_by_edit_distance(query, top_n=1)
        if closest and closest[0] != query.lower():
            dist = self._edit_distance(query.lower(), closest[0])
            if dist <= 2 and ' ' not in query:
                suggestion = closest[0]
                results = run_like_query(suggestion)
                if results:
                    return results, suggestion

        # Gibberish detection -> skip to fallback
        if self._is_gibberish(query.lower()):
            if area or district or food_type:
                cursor.execute(f"""
                    SELECT * FROM posts 
                    WHERE {base_where}
                    ORDER BY expiry_date ASC
                    LIMIT 100
                """, params)
                results = cursor.fetchall()
                return results, suggestion
            else:
                cursor.execute("""
                    SELECT * FROM posts 
                    WHERE status = 'available'
                    AND expiry_date >= date('now')
                    ORDER BY expiry_date ASC
                    LIMIT 100
                """)
                results = cursor.fetchall()
                return results, suggestion

        # Layer 3: Semantic expansion (Sentence-BERT)
        similar_names = self.get_similar_foods_sbert(query, top_n=5, min_similarity=0.3)
        merged_results = []
        seen_post_ids = set()
        for expanded_word in similar_names:
            results = run_like_query(expanded_word)
            for row in results:
                if row['id'] not in seen_post_ids:
                    seen_post_ids.add(row['id'])
                    merged_results.append(row)
        if merged_results:
            return merged_results, suggestion

        # Layer 4: Category fallback (Naive Bayes)
        inferred_type = self.infer_type_naive_bayes(query)
        if inferred_type and not food_type:
            cursor.execute(f"""
                SELECT * FROM posts 
                WHERE food_type = ?
                AND {base_where}
                ORDER BY expiry_date ASC
                LIMIT 100
            """, (inferred_type,) + tuple(params))
            results = cursor.fetchall()
            if results:
                return results, suggestion

        # Layer 5: Filtered fallback (ignore keyword, keep filters)
        if area or district or food_type:
            cursor.execute(f"""
                SELECT * FROM posts 
                WHERE {base_where}
                ORDER BY expiry_date ASC
                LIMIT 100
            """, params)
            results = cursor.fetchall()
            if results:
                return results, suggestion

        # Layer 6: Popular fallback (no keyword, no filters)
        cursor.execute("""
            SELECT * FROM posts 
            WHERE status = 'available'
            AND expiry_date >= date('now')
            ORDER BY expiry_date ASC
            LIMIT 100
        """)
        results = cursor.fetchall()
        return results, suggestion