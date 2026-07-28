import sqlite3
import pandas as pd
from werkzeug.security import generate_password_hash
from datetime import datetime
import os
import random
from clean_seed_data import clean_and_save_seed_data
from demo_posts import generate_demo_posts, FIXED_POST_FOODS

DB_PATH = '/home/ashleyyau/mysite/foodshare.db'
CSV_PATH = 'cleaned_seed_foods.csv'

# Check if table exists
def table_exists(conn, table_name):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

# Add lat/lng columns if missing
def add_coordinate_columns(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(posts)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'latitude' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN latitude REAL")
    if 'longitude' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN longitude REAL")
    conn.commit()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    
    if table_exists(conn, 'users'):
        add_coordinate_columns(conn)
        print("Database initialized.")
        conn.close()
        return
    
    cursor.execute("DROP TABLE IF EXISTS reports")
    cursor.execute("DROP TABLE IF EXISTS user_views")
    cursor.execute("DROP TABLE IF EXISTS messages")
    cursor.execute("DROP TABLE IF EXISTS posts")
    cursor.execute("DROP TABLE IF EXISTS seed_foods")
    cursor.execute("DROP TABLE IF EXISTS users")
    
    cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            area TEXT,
            district TEXT,
            estate_building TEXT,
            is_admin BOOLEAN DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            food_name TEXT NOT NULL,
            food_type TEXT NOT NULL,
            description TEXT,
            area TEXT NOT NULL,
            district TEXT NOT NULL,
            estate_building TEXT,
            expiry_date DATE NOT NULL,
            image_path TEXT,
            status TEXT DEFAULT 'available',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            latitude REAL,
            longitude REAL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE user_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            food_type TEXT NOT NULL,
            viewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE seed_foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name TEXT NOT NULL,
            food_type TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    if not os.path.exists(CSV_PATH):
        clean_and_save_seed_data()
    
    try:
        df = pd.read_csv(CSV_PATH, encoding='latin-1')
        for _, row in df.iterrows():
            cursor.execute("INSERT INTO seed_foods (food_name, food_type) VALUES (?, ?)", (row['food_name'], row['food_type']))
    except Exception as e:
        print(f"Error loading CSV: {e}. Using fallback seed data.")
        fallback = [('Apple','fruit'),('Banana','fruit'),('Baguette','bread'),('Cheesecake','cake'),('Broccoli','vegetable'),('Pizza','meal')]
        cursor.executemany("INSERT INTO seed_foods (food_name, food_type) VALUES (?, ?)", fallback)
    
    for food_name, food_type in FIXED_POST_FOODS:
        cursor.execute("SELECT 1 FROM seed_foods WHERE LOWER(food_name) = LOWER(?)", (food_name,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO seed_foods (food_name, food_type) VALUES (?, ?)", (food_name, food_type))
    conn.commit()
    
    admin_hash = generate_password_hash('123')
    cursor.execute('INSERT INTO users (username, password_hash, area, district, estate_building, is_admin) VALUES (?, ?, ?, ?, ?, ?)',
                   ('admin', admin_hash, '', '', '', 1))
    
    poster_users = ['poster1', 'poster2', 'poster3', 'poster4']
    poster_ids = []
    for username in poster_users:
        pw_hash = generate_password_hash('123')
        if username == 'poster1':
            area, district, estate = 'Kowloon', 'Yau Tsim Mong', 'The Masterpiece'
        else:
            area = district = estate = ''
        cursor.execute('INSERT INTO users (username, password_hash, area, district, estate_building, is_admin) VALUES (?, ?, ?, ?, ?, ?)',
                       (username, pw_hash, area, district, estate, 0))
        cursor.execute("SELECT last_insert_rowid()")
        poster_ids.append(cursor.fetchone()[0])
    conn.commit()
    
    generate_demo_posts(conn, poster_ids)
    
    # Insert sample reports for demo
    cursor.execute("SELECT id, user_id FROM posts WHERE status = 'available' AND expiry_date >= date('now') LIMIT 3")
    sample_posts = cursor.fetchall()
    cursor.execute("SELECT id FROM users WHERE username IN ('poster2', 'poster3', 'poster4')")
    reporters = cursor.fetchall()
    if sample_posts and reporters:
        reasons = ['Expired food', 'Wrong location', 'Spam', 'Offensive content', 'Fake post']
        for i, post in enumerate(sample_posts):
            reporter = reporters[i % len(reporters)]
            reason = random.choice(reasons)
            cursor.execute("SELECT id FROM reports WHERE post_id = ? AND user_id = ?", (post[0], reporter[0]))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO reports (post_id, user_id, reason) VALUES (?, ?, ?)",
                               (post[0], reporter[0], reason))
    conn.commit()
    
    print("Database initialized.")
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_user(username, password_hash, area, district, estate_building):
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (username, password_hash, area, district, estate_building) VALUES (?, ?, ?, ?, ?)',
                     (username, password_hash, area, district, estate_building))
        conn.commit()
        user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user

def is_admin(user_id):
    conn = get_db()
    row = conn.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return row and row['is_admin'] == 1

def create_post(user_id, food_name, food_type, description, area, district, estate_building, expiry_date, image_path, latitude=None, longitude=None):
    conn = get_db()
    conn.execute('''
        INSERT INTO posts (user_id, food_name, food_type, description, area, district, estate_building, expiry_date, image_path, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, food_name, food_type, description, area, district, estate_building, expiry_date, image_path, latitude, longitude))
    conn.commit()
    post_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return post_id

def add_message(post_id, user_id, content):
    conn = get_db()
    conn.execute('INSERT INTO messages (post_id, user_id, content) VALUES (?, ?, ?)', (post_id, user_id, content))
    conn.commit()
    conn.close()

def log_user_view(user_id, food_type):
    conn = get_db()
    conn.execute('INSERT INTO user_views (user_id, food_type) VALUES (?, ?)', (user_id, food_type))
    conn.commit()
    conn.close()

def get_user_preferred_food_types(user_id, top_n=5):
    conn = get_db()
    rows = conn.execute('''
        SELECT food_type, COUNT(*) as view_count
        FROM user_views
        WHERE user_id = ?
        GROUP BY food_type
        ORDER BY view_count DESC
        LIMIT ?
    ''', (user_id, top_n)).fetchall()
    conn.close()
    return [row['food_type'] for row in rows]

def add_report(post_id, user_id, reason):
    conn = get_db()
    existing = conn.execute('SELECT id FROM reports WHERE post_id = ? AND user_id = ?', (post_id, user_id)).fetchone()
    if existing:
        conn.close()
        return False
    conn.execute('INSERT INTO reports (post_id, user_id, reason) VALUES (?, ?, ?)', (post_id, user_id, reason))
    conn.commit()
    conn.close()
    return True

if __name__ == '__main__':
    init_db()