# Generate 100 demo posts with fixed food list and district mapping
from datetime import date, timedelta, datetime
from coordinates import get_coordinates

FIXED_POST_FOODS = [
    ('Baguette', 'bread'), ('Croissant', 'bread'), ('Sourdough', 'bread'), ('Ciabatta', 'bread'), ('Focaccia', 'bread'),
    ('Pita', 'bread'), ('Naan', 'bread'), ('Pretzel', 'bread'), ('Bagel', 'bread'), ('Brioche', 'bread'),
    ('Rye Bread', 'bread'), ('White Bread', 'bread'), ('Garlic Bread', 'bread'), ('French Toast', 'bread'), ('Bread Roll', 'bread'),
    ('Bun', 'bread'), ('Loaf', 'bread'), ('Breadstick', 'bread'), ('Pumpernickel', 'bread'), ('Multigrain Bread', 'bread'),
    ('Cheesecake', 'cake'), ('Brownie', 'cake'), ('Cupcake', 'cake'), ('Muffin', 'cake'), ('Pound Cake', 'cake'),
    ('Sponge Cake', 'cake'), ('Angel Food Cake', 'cake'), ('Carrot Cake', 'cake'), ('Lemon Cake', 'cake'), ('Coffee Cake', 'cake'),
    ('Red Velvet Cake', 'cake'), ('Fruitcake', 'cake'), ('Marble Cake', 'cake'), ('Chiffon Cake', 'cake'), ('Butter Cake', 'cake'),
    ('Coconut Cake', 'cake'), ('Almond Cake', 'cake'), ('Honey Cake', 'cake'), ('Orange Cake', 'cake'), ('Pineapple Cake', 'cake'),
    ('Apple', 'fruit'), ('Banana', 'fruit'), ('Orange', 'fruit'), ('Grapes', 'fruit'), ('Watermelon', 'fruit'),
    ('Strawberry', 'fruit'), ('Blueberry', 'fruit'), ('Raspberry', 'fruit'), ('Mango', 'fruit'), ('Pineapple', 'fruit'),
    ('Peach', 'fruit'), ('Pear', 'fruit'), ('Plum', 'fruit'), ('Cherry', 'fruit'), ('Kiwi', 'fruit'),
    ('Lemon', 'fruit'), ('Lime', 'fruit'), ('Grapefruit', 'fruit'), ('Avocado', 'fruit'), ('Pomegranate', 'fruit'),
    ('Pizza', 'meal'), ('Burger', 'meal'), ('Sushi', 'meal'), ('Ramen', 'meal'), ('Pasta', 'meal'),
    ('Fried Rice', 'meal'), ('Steak', 'meal'), ('Salmon', 'meal'), ('Tacos', 'meal'), ('Lasagna', 'meal'),
    ('Curry', 'meal'), ('Stew', 'meal'), ('Omelette', 'meal'), ('Sandwich', 'meal'), ('Salad', 'meal'),
    ('Soup', 'meal'), ('Noodle', 'meal'), ('Rice Bowl', 'meal'), ('Quesadilla', 'meal'), ('Falafel', 'meal'),
    ('Broccoli', 'vegetable'), ('Carrot', 'vegetable'), ('Spinach', 'vegetable'), ('Tomato', 'vegetable'), ('Cucumber', 'vegetable'),
    ('Lettuce', 'vegetable'), ('Bell Pepper', 'vegetable'), ('Cauliflower', 'vegetable'), ('Zucchini', 'vegetable'), ('Eggplant', 'vegetable'),
    ('Cabbage', 'vegetable'), ('Celery', 'vegetable'), ('Asparagus', 'vegetable'), ('Green Bean', 'vegetable'), ('Peas', 'vegetable'),
    ('Corn', 'vegetable'), ('Radish', 'vegetable'), ('Beetroot', 'vegetable'), ('Onion', 'vegetable'), ('Garlic', 'vegetable')
]

DISTRICTS_INFO = [
    ('Hong Kong Island', 'Central and Western', 'Mid-Levels Garden'),
    ('Hong Kong Island', 'Wan Chai', 'The Avenue'),
    ('Hong Kong Island', 'Eastern', 'Kornhill Garden'),
    ('Hong Kong Island', 'Southern', 'South Horizons'),
    ('Kowloon', 'Yau Tsim Mong', 'The Masterpiece'),
    ('Kowloon', 'Sham Shui Po', 'Beacon Heights'),
    ('Kowloon', 'Kowloon City', 'Kadoorie Hill'),
    ('Kowloon', 'Wong Tai Sin', 'Fung Tak Estate'),
    ('Kowloon', 'Kwun Tong', 'Laguna City'),
    ('New Territories', 'Tsuen Wan', 'Discovery Park'),
    ('New Territories', 'Tuen Mun', 'Melody Garden'),
    ('New Territories', 'Yuen Long', 'YOHO Town'),
    ('New Territories', 'North', 'Avon Park'),
    ('New Territories', 'Tai Po', 'Tai Po Centre'),
    ('New Territories', 'Sha Tin', 'City One Shatin'),
    ('New Territories', 'Sai Kung', 'Marina Cove'),
    ('New Territories', 'Islands', 'Caribbean Coast'),
    ('New Territories', 'Kwai Tsing', 'Kwai Fong Estate')
]

def generate_demo_posts(conn, poster_ids):
    cursor = conn.cursor()
    base_expiry = date(2026, 9, 1)

    for i, (food_name, food_type) in enumerate(FIXED_POST_FOODS):
        user_index = i // 25
        user_id = poster_ids[user_index]
        district_idx = i % len(DISTRICTS_INFO)
        area, district, estate = DISTRICTS_INFO[district_idx]
        expiry_date = (base_expiry + timedelta(days=i)).strftime('%Y-%m-%d')
        description = f"1 portion of {food_name}"
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        lat, lng = get_coordinates(district, estate)

        img_filename = f"{food_name.replace(' ', '_')}.jpg"

        cursor.execute('''
            INSERT INTO posts (user_id, food_name, food_type, description, area, district, estate_building, expiry_date, image_path, status, created_at, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, food_name, food_type, description, area, district, estate, expiry_date, img_filename, 'available', created_at, lat, lng))

    conn.commit()