from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import database as db
from search import SearchEngine
from datetime import datetime, date, timezone, timedelta
from functools import wraps
from coordinates import get_coordinates   # NEW IMPORT

app = Flask(__name__)
app.secret_key = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'static/photos'

db.init_db()

# SearchEngine lazy init
search_engine = None

def get_search_engine():
    global search_engine
    if search_engine is None:
        from search import SearchEngine
        search_engine = SearchEngine()
    return search_engine

def mark_expiring_soon(posts):
    """Mark posts expiring within 2 days."""
    today = date.today()
    for post in posts:
        expiry_date = date.fromisoformat(post['expiry_date'])
        post['is_expiring_soon'] = (expiry_date - today).days <= 2
    return posts

def to_hk_time(utc_str):
    """Convert UTC to Hong Kong time (UTC+8)."""
    if not utc_str:
        return utc_str
    utc_dt = datetime.strptime(utc_str, '%Y-%m-%d %H:%M:%S')
    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    hk_tz = timezone(timedelta(hours=8))
    hk_dt = utc_dt.astimezone(hk_tz)
    return hk_dt.strftime('%Y-%m-%d %H:%M:%S')

def get_expired_available_posts(user_id):
    """Return expired available posts (id, name)."""
    conn = db.get_db()
    today = date.today().isoformat()
    rows = conn.execute('''
        SELECT id, food_name FROM posts
        WHERE user_id = ? AND status = 'available' AND expiry_date < ?
    ''', (user_id, today)).fetchall()
    conn.close()
    return [(row['id'], row['food_name']) for row in rows]

def admin_required(f):
    """Admin login decorator."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'danger')
            return redirect(url_for('login', next=request.full_path))
        if not db.is_admin(session['user_id']):
            flash('Admin access required.', 'danger')
            return redirect(url_for('search'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return redirect(url_for('search'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    area = request.args.get('area', '')
    district = request.args.get('district', '')
    food_type = request.args.get('food_type', '') or None

    conn = db.get_db()
    cursor = conn.cursor()
    user_id = session.get('user_id')
    exclude_self = user_id and not db.is_admin(user_id)

    total_available_sql = "SELECT COUNT(*) FROM posts WHERE status = 'available' AND expiry_date >= date('now')"
    if exclude_self:
        total_available_sql += " AND user_id != ?"
        total_available = conn.execute(total_available_sql, (user_id,)).fetchone()[0]
    else:
        total_available = conn.execute(total_available_sql).fetchone()[0]

    # Case 1: no keyword, no filters
    if not query and not area and not district and not food_type:
        base_sql = """
            SELECT posts.*, users.username
            FROM posts
            JOIN users ON posts.user_id = users.id
            WHERE posts.status = 'available' AND posts.expiry_date >= date('now')
        """
        params = []
        if exclude_self:
            base_sql += " AND posts.user_id != ?"
            params.append(user_id)

        preferred_types = []
        if user_id:
            preferred_types = db.get_user_preferred_food_types(user_id, top_n=5)

        if preferred_types:
            placeholders = ','.join(['?'] * len(preferred_types))
            order_by = f"CASE WHEN posts.food_type IN ({placeholders}) THEN 0 ELSE 1 END, posts.expiry_date ASC"
            sql = base_sql + f" ORDER BY {order_by} LIMIT 100"
            cursor.execute(sql, params + preferred_types)
        else:
            sql = base_sql + " ORDER BY posts.expiry_date ASC LIMIT 100"
            cursor.execute(sql, params)

        results = cursor.fetchall()
        posts = [dict(row) for row in results]
        posts = mark_expiring_soon(posts)
        conn.close()
        return render_template('search.html', query='', posts=posts, area=area, district=district, food_type=food_type, is_fallback=False, correction_suggestion=None)

    # Case 2: no keyword, only filters
    if not query and (area or district or food_type):
        base_query = '''
            SELECT posts.*, users.username
            FROM posts
            JOIN users ON posts.user_id = users.id
            WHERE posts.status = 'available' AND posts.expiry_date >= date('now')
        '''
        params = []
        if area:
            base_query += ' AND posts.area = ?'
            params.append(area)
        if district:
            base_query += ' AND posts.district = ?'
            params.append(district)
        if food_type:
            base_query += ' AND posts.food_type = ?'
            params.append(food_type)
        if exclude_self:
            base_query += ' AND posts.user_id != ?'
            params.append(user_id)
        base_query += ' ORDER BY posts.expiry_date ASC LIMIT 100'
        rows = conn.execute(base_query, params).fetchall()
        posts = [dict(row) for row in rows]
        posts = mark_expiring_soon(posts)
        conn.close()
        return render_template('search.html', query='', posts=posts, area=area, district=district, food_type=food_type, is_fallback=False, correction_suggestion=None)

    # Case 3: normal search with keyword
    engine = get_search_engine()
    results, suggestion = engine.search(query, cursor, area=area, district=district, food_type=food_type)

    posts = []
    for row in results:
        post = dict(row)
        user = conn.execute('SELECT username FROM users WHERE id = ?', (post['user_id'],)).fetchone()
        post['username'] = user['username'] if user else 'unknown'
        posts.append(post)
    if exclude_self:
        posts = [p for p in posts if p['user_id'] != user_id]
    posts = mark_expiring_soon(posts)

    is_fallback = False
    if query and not area and not district and not food_type:
        if len(posts) == total_available:
            is_fallback = True

    conn.close()
    return render_template('search.html', query=query, posts=posts, area=area, district=district,
                           food_type=food_type or '', is_fallback=is_fallback, correction_suggestion=suggestion)

@app.route('/map-data')
def map_data():
    conn = db.get_db()
    posts = conn.execute('''
        SELECT id, food_name, estate_building, latitude, longitude
        FROM posts
        WHERE status = 'available' AND expiry_date >= date('now')
          AND latitude IS NOT NULL AND longitude IS NOT NULL
    ''').fetchall()
    conn.close()
    return jsonify({'posts': [dict(row) for row in posts]})

@app.route('/post/<int:post_id>')
def view_post(post_id):
    conn = db.get_db()
    post = conn.execute('''
        SELECT posts.*, users.username
        FROM posts
        JOIN users ON posts.user_id = users.id
        WHERE posts.id = ?
    ''', (post_id,)).fetchone()
    if not post:
        conn.close()
        return redirect(url_for('search'))
    
    if 'user_id' in session:
        db.log_user_view(session['user_id'], post['food_type'])
    
    messages = conn.execute('''
        SELECT m.*, u.username FROM messages m
        JOIN users u ON m.user_id = u.id
        WHERE m.post_id = ?
        ORDER BY m.created_at ASC
    ''', (post_id,)).fetchall()
    messages = [dict(msg) for msg in messages]
    for msg in messages:
        if msg['created_at']:
            msg['created_at'] = to_hk_time(msg['created_at'])
    
    engine = get_search_engine()
    similar = engine.get_similar_foods(post['food_name'], top_n=5)
    recs = []
    if similar:
        placeholders = ','.join(['?'] * len(similar))
        recs = conn.execute(f"""
            SELECT posts.*, users.username
            FROM posts
            JOIN users ON posts.user_id = users.id
            WHERE posts.food_name IN ({placeholders})
            AND posts.status = 'available'
            AND posts.expiry_date >= date('now')
            AND posts.id != ?
            ORDER BY posts.expiry_date ASC
            LIMIT 5
        """, similar + [post_id]).fetchall()
        recs = [dict(r) for r in recs]
        recs = mark_expiring_soon(recs)
    
    is_admin = False
    if 'user_id' in session:
        is_admin = db.is_admin(session['user_id'])
    
    conn.close()
    return render_template('post_detail.html', post=post, messages=messages, recommendations=recs, is_admin=is_admin)

@app.route('/report/<int:post_id>', methods=['POST'])
def report_post(post_id):
    if 'user_id' not in session:
        flash('Please login to report.', 'danger')
        return redirect(url_for('login', next=request.full_path))
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('Please provide a reason.', 'danger')
        return redirect(url_for('view_post', post_id=post_id))
    success = db.add_report(post_id, session['user_id'], reason)
    if success:
        flash('Thank you for reporting.', 'success')
    else:
        flash('You have already reported this post.', 'warning')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    next_url = request.args.get('next') or request.form.get('next')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        area = request.form['area']
        district = request.form['district']
        estate_building = request.form.get('estate_building', '')
        
        if 'disclaimer' not in request.form:
            return render_template('register_login.html', 
                                   register_error='You must acknowledge the disclaimer to register.',
                                   form_username=username,
                                   form_area=area,
                                   form_district=district,
                                   form_estate_building=estate_building,
                                   next=next_url)
        
        pwhash = generate_password_hash(password)
        user_id = db.create_user(username, pwhash, area, district, estate_building)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            session['is_admin'] = False
            if next_url:
                return redirect(next_url)
            return redirect(url_for('search'))
        else:
            return render_template('register_login.html',
                                   register_error='Username already exists',
                                   form_username=username,
                                   form_area=area,
                                   form_district=district,
                                   form_estate_building=estate_building,
                                   next=next_url)
    return render_template('register_login.html', next=next_url)

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next') or request.form.get('next')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = db.get_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            # Flash expired posts warning with links
            expired_posts = get_expired_available_posts(user['id'])
            if expired_posts:
                links = []
                for pid, name in expired_posts:
                    links.append(f'<a href="{url_for("my_posts", highlight=pid)}">{name}</a>')
                flash(f'Your post(s) {", ".join(links)} have expired and are hidden. You can extend them using the "Extend" button.', 'warning')
            if next_url:
                return redirect(next_url)
            return redirect(url_for('search'))
        else:
            return render_template('register_login.html', login_error='Invalid username or password', next=next_url)
    return render_template('register_login.html', next=next_url)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('search'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.full_path))
    user_id = session['user_id']
    conn = db.get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if not user:
        return redirect(url_for('login'))
    return render_template('profile.html', user=user)

@app.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.full_path))
    user_id = session['user_id']
    conn = db.get_db()
    if request.method == 'POST':
        area = request.form['area']
        district = request.form['district']
        estate_building = request.form.get('estate_building', '')
        conn.execute('UPDATE users SET area=?, district=?, estate_building=? WHERE id=?',
                     (area, district, estate_building, user_id))
        conn.commit()
        conn.close()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('profile'))
    else:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        return render_template('edit_profile.html', user=user)

@app.route('/my_posts')
def my_posts():
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.full_path))
    user_id = session['user_id']
    conn = db.get_db()
    posts = conn.execute('''
        SELECT * FROM posts 
        WHERE user_id = ? 
        ORDER BY expiry_date ASC
    ''', (user_id,)).fetchall()
    posts = [dict(row) for row in posts]
    
    # Flash expired posts warning with links
    expired_posts = get_expired_available_posts(user_id)
    if expired_posts:
        links = []
        for pid, name in expired_posts:
            links.append(f'<a href="{url_for("my_posts", highlight=pid)}">{name}</a>')
        flash(f'Your post(s) {", ".join(links)} have expired and are hidden. You can extend them using the "Extend" button.', 'warning')
    
    posts = mark_expiring_soon(posts)
    
    highlight_id = request.args.get('highlight', type=int)
    
    conn.close()
    return render_template('my_posts.html', posts=posts, highlight_id=highlight_id)

@app.route('/post/new', methods=['GET', 'POST'])
def create_post():
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.full_path))
    if request.method == 'POST':
        user_id = session['user_id']
        food_name = request.form['food_name']
        food_type = request.form['food_type']
        description = request.form.get('description', '')
        area = request.form['area']
        district = request.form['district']
        estate_building = request.form.get('estate_building', '')
        expiry_date = request.form['expiry_date']
        image_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                unique_name = f"{user_id}_{int(datetime.now().timestamp())}_{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                image_path = unique_name
        
        # Get coordinates based on district and building
        lat, lng = get_coordinates(district, estate_building)
        
        post_id = db.create_post(user_id, food_name, food_type, description, area, district, estate_building, expiry_date, image_path, lat, lng)
        return redirect(url_for('view_post', post_id=post_id))
    return render_template('create_post.html')

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
def edit_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.full_path))
    conn = db.get_db()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post or post['user_id'] != session['user_id']:
        conn.close()
        return redirect(url_for('search'))
    
    if request.method == 'POST':
        food_name = request.form['food_name']
        food_type = request.form['food_type']
        description = request.form.get('description', '')
        area = request.form['area']
        district = request.form['district']
        estate_building = request.form.get('estate_building', '')
        expiry_date = request.form['expiry_date']
        status = request.form['status']
        
        image_path = post['image_path']
        file = request.files.get('image')
        delete_image = request.form.get('delete_image') == '1'
        
        if file and file.filename:
            if image_path:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_path)
                if os.path.exists(old_path):
                    os.remove(old_path)
            filename = secure_filename(file.filename)
            unique_name = f"{session['user_id']}_{int(datetime.now().timestamp())}_{filename}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            image_path = unique_name
        elif delete_image and image_path:
            if image_path.startswith(f"{session['user_id']}_"):
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_path)
                if os.path.exists(old_path):
                    os.remove(old_path)
            image_path = None
        
        # Get coordinates based on district and building
        lat, lng = get_coordinates(district, estate_building)
        
        conn.execute('''
            UPDATE posts 
            SET food_name=?, food_type=?, description=?, area=?, district=?, estate_building=?, expiry_date=?, status=?, image_path=?, latitude=?, longitude=?
            WHERE id=?
        ''', (food_name, food_type, description, area, district, estate_building, expiry_date, status, image_path, lat, lng, post_id))
        conn.commit()
        conn.close()
        return redirect(url_for('my_posts'))
    
    conn.close()
    return render_template('edit_post.html', post=post)

@app.route('/post/<int:post_id>/delete', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.full_path))
    conn = db.get_db()
    post = conn.execute('SELECT user_id, image_path FROM posts WHERE id = ?', (post_id,)).fetchone()
    is_admin = db.is_admin(session['user_id'])
    if post and (post['user_id'] == session['user_id'] or is_admin):
        # Skip file deletion to keep demo images
        conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        conn.commit()
        flash('Post deleted successfully.', 'success')
    else:
        flash('You are not authorized to delete this post.', 'danger')
    conn.close()
    return redirect(url_for('my_posts'))

@app.route('/post/<int:post_id>/extend', methods=['POST'])
def extend_post(post_id):
    if 'user_id' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login', next=request.full_path))
    days = request.form.get('days', type=int)
    if days is None or days <= 0:
        days = 3
    conn = db.get_db()
    post = conn.execute('SELECT user_id, expiry_date FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post or post['user_id'] != session['user_id']:
        conn.close()
        flash('You are not authorized to extend this post.', 'danger')
        return redirect(url_for('my_posts'))
    
    current_expiry = date.fromisoformat(post['expiry_date'])
    new_expiry = current_expiry + timedelta(days=days)
    conn.execute('UPDATE posts SET expiry_date = ? WHERE id = ?', (new_expiry.isoformat(), post_id))
    conn.commit()
    conn.close()
    flash(f'Expiry date extended by {days} day(s) to {new_expiry.isoformat()}.', 'success')
    return redirect(url_for('my_posts'))

@app.route('/post/<int:post_id>/message', methods=['POST'])
def add_message(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.full_path))
    content = request.form['content']
    db.add_message(post_id, session['user_id'], content)
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/admin')
@admin_required
def admin_panel():
    conn = db.get_db()
    # Dashboard stats
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today = date.today().isoformat()
    expired_available = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE status = 'available' AND expiry_date < ?", (today,)
    ).fetchone()[0]
    # Posts by food type
    food_type_counts = conn.execute(
        "SELECT food_type, COUNT(*) FROM posts GROUP BY food_type"
    ).fetchall()
    food_types = [row[0] for row in food_type_counts]
    food_counts = [row[1] for row in food_type_counts]
    # Last 7 days trend
    seven_days_ago = (date.today() - timedelta(days=6)).isoformat()
    trend = conn.execute(
        "SELECT DATE(created_at) as post_date, COUNT(*) FROM posts WHERE created_at >= ? GROUP BY DATE(created_at) ORDER BY post_date",
        (seven_days_ago,)
    ).fetchall()
    trend_labels = [row[0] for row in trend]
    trend_values = [row[1] for row in trend]
    
    # Reports
    reports = conn.execute('''
        SELECT r.*, p.food_name, p.user_id, 
               u_reporter.username as reporter_name, 
               u_author.username as post_author
        FROM reports r
        JOIN posts p ON r.post_id = p.id
        JOIN users u_reporter ON r.user_id = u_reporter.id
        JOIN users u_author ON p.user_id = u_author.id
        ORDER BY r.created_at DESC
    ''').fetchall()
    
    reports_list = []
    for report in reports:
        report_dict = dict(report)
        if report_dict.get('created_at'):
            report_dict['created_at'] = to_hk_time(report_dict['created_at'])
        reports_list.append(report_dict)
    
    users = conn.execute('SELECT id, username, is_admin FROM users ORDER BY id').fetchall()
    conn.close()
    return render_template('admin.html', 
                           reports=reports_list, 
                           users=users,
                           total_posts=total_posts,
                           total_users=total_users,
                           expired_available=expired_available,
                           food_types=food_types,
                           food_counts=food_counts,
                           trend_labels=trend_labels,
                           trend_values=trend_values)

@app.route('/admin/delete_post/<int:post_id>', methods=['POST'])
@admin_required
def admin_delete_post(post_id):
    conn = db.get_db()
    post = conn.execute('SELECT image_path FROM posts WHERE id = ?', (post_id,)).fetchone()
    # Skip physical deletion to preserve demo images
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    flash('Post deleted successfully.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/ban_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_ban_user(user_id):
    conn = db.get_db()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('User banned.', 'success')
    return redirect(url_for('admin_panel'))