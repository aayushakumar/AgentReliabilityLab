-- =========================================================
-- Seed data for SQL Benchmark database
-- =========================================================

-- Categories
INSERT INTO categories (name, slug) VALUES
    ('Electronics', 'electronics'),
    ('Books', 'books'),
    ('Clothing', 'clothing'),
    ('Home & Garden', 'home-garden'),
    ('Sports', 'sports');

-- Customers (20)
INSERT INTO customers (name, email, country, tier, created_at) VALUES
    ('Alice Johnson',    'alice@example.com',   'US', 'vip',      '2023-01-15'),
    ('Bob Smith',        'bob@example.com',     'UK', 'premium',  '2023-02-20'),
    ('Carol Davis',      'carol@example.com',   'US', 'standard', '2023-03-10'),
    ('David Wilson',     'david@example.com',   'CA', 'premium',  '2023-01-05'),
    ('Emma Brown',       'emma@example.com',    'AU', 'standard', '2023-04-18'),
    ('Frank Miller',     'frank@example.com',   'US', 'vip',      '2022-11-30'),
    ('Grace Lee',        'grace@example.com',   'US', 'standard', '2023-05-22'),
    ('Henry Taylor',     'henry@example.com',   'UK', 'premium',  '2023-06-01'),
    ('Iris Martinez',    'iris@example.com',    'MX', 'standard', '2023-07-14'),
    ('Jack Anderson',    'jack@example.com',    'US', 'vip',      '2022-12-25'),
    ('Karen Thomas',     'karen@example.com',   'CA', 'standard', '2023-08-09'),
    ('Liam Jackson',     'liam@example.com',    'US', 'premium',  '2023-09-03'),
    ('Mia White',        'mia@example.com',     'UK', 'standard', '2023-10-11'),
    ('Noah Harris',      'noah@example.com',    'US', 'standard', '2023-11-20'),
    ('Olivia Martin',    'olivia@example.com',  'FR', 'premium',  '2023-12-01'),
    ('Peter Garcia',     'peter@example.com',   'US', 'standard', '2024-01-07'),
    ('Quinn Robinson',   'quinn@example.com',   'AU', 'vip',      '2024-02-14'),
    ('Rachel Clark',     'rachel@example.com',  'US', 'standard', '2024-03-22'),
    ('Sam Lewis',        'sam@example.com',     'CA', 'premium',  '2024-04-05'),
    ('Tina Walker',      'tina@example.com',    'US', 'standard', '2024-05-18');

-- Products (15)
INSERT INTO products (name, description, price, category_id, stock, is_active) VALUES
    ('MacBook Pro 14"',   'Apple laptop M3',       1999.99, 1, 50,  1),
    ('iPhone 15',         'Apple smartphone',       999.99, 1, 200, 1),
    ('AirPods Pro',       'Wireless earbuds',       249.99, 1, 300, 1),
    ('Python Cookbook',   'Advanced Python recipes', 49.99, 2, 150, 1),
    ('Clean Code',        'Software craftsmanship',  34.99, 2, 200, 1),
    ('Running Shoes',     'Nike Air Max',           129.99, 5, 100, 1),
    ('Yoga Mat',          'Non-slip 6mm mat',        39.99, 5, 250, 1),
    ('Coffee Maker',      'Drip coffee machine',     89.99, 4, 80,  1),
    ('Smart TV 55"',      '4K OLED smart TV',       799.99, 1, 30,  1),
    ('Wireless Keyboard', 'Mechanical Bluetooth',    79.99, 1, 120, 1),
    ('T-Shirt Basic',     '100% cotton',             19.99, 3, 500, 1),
    ('Denim Jeans',       'Slim fit denim',          59.99, 3, 300, 1),
    ('Garden Hose',       '50ft expandable hose',    29.99, 4, 150, 0),
    ('Desk Lamp',         'LED adjustable lamp',     44.99, 4, 200, 1),
    ('Gaming Mouse',      'RGB gaming mouse',        69.99, 1, 180, 1);

-- Orders (30)
INSERT INTO orders (customer_id, status, total_amount, created_at, shipped_at) VALUES
    (1,  'completed',  2249.97, '2024-01-10', '2024-01-12'),
    (2,  'completed',   164.98, '2024-01-15', '2024-01-17'),
    (3,  'completed',  1079.98, '2024-01-20', '2024-01-22'),
    (4,  'cancelled',   249.99, '2024-02-01', NULL),
    (5,  'completed',    84.98, '2024-02-05', '2024-02-07'),
    (6,  'completed',  1999.99, '2024-02-10', '2024-02-12'),
    (7,  'refunded',    129.99, '2024-02-15', '2024-02-17'),
    (8,  'completed',   879.98, '2024-03-01', '2024-03-03'),
    (9,  'processing',  289.98, '2024-03-10', NULL),
    (10, 'completed',  3249.96, '2024-03-15', '2024-03-17'),
    (1,  'completed',   999.99, '2024-03-20', '2024-03-22'),
    (2,  'completed',   354.96, '2024-04-01', '2024-04-03'),
    (11, 'completed',   149.98, '2024-04-05', '2024-04-07'),
    (12, 'completed',   799.99, '2024-04-10', '2024-04-12'),
    (13, 'pending',     219.98, '2024-04-15', NULL),
    (14, 'completed',    79.98, '2024-04-20', '2024-04-22'),
    (15, 'completed',  2049.98, '2024-05-01', '2024-05-03'),
    (16, 'completed',   199.97, '2024-05-05', '2024-05-07'),
    (17, 'cancelled',   479.97, '2024-05-10', NULL),
    (18, 'completed',   919.98, '2024-05-15', '2024-05-17'),
    (4,  'completed',  1249.98, '2024-05-20', '2024-05-22'),
    (6,  'completed',   329.97, '2024-06-01', '2024-06-03'),
    (10, 'completed',   249.99, '2024-06-05', '2024-06-07'),
    (1,  'processing',  799.99, '2024-06-10', NULL),
    (19, 'completed',  1069.98, '2024-06-12', '2024-06-14'),
    (20, 'completed',   169.98, '2024-06-13', '2024-06-15'),
    (3,  'completed',   399.96, '2024-06-14', '2024-06-16'),
    (5,  'completed',   799.99, '2024-06-14', '2024-06-16'),
    (8,  'completed',   299.97, '2024-06-14', '2024-06-15'),
    (12, 'completed',   189.98, '2024-06-15', NULL);

-- Order Items
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1,  1, 1, 1999.99), (1,  3, 1, 249.98),
    (2,  4, 1,  49.99),  (2,  5, 1,  34.99),  (2, 7, 2, 39.99),
    (3,  2, 1,  999.99), (3,  3, 1, 249.99),  (3, 10, 1, 79.99),
    (4,  3, 1,  249.99),
    (5,  4, 1,   49.99), (5,  5, 1,  34.99),
    (6,  1, 1, 1999.99),
    (7,  6, 1,  129.99),
    (8,  9, 1,  799.99), (8, 10, 1,  79.99),
    (9,  7, 2,   39.99), (9, 14, 1,  44.99),  (9, 15, 1, 69.99),
    (10, 1, 1, 1999.99), (10,  2, 1, 999.99),  (10, 3, 1, 249.99),
    (11, 2, 1,  999.99),
    (12, 4, 2,   49.99), (12, 5, 2,  34.99),   (12, 7, 2, 39.99),
    (13, 6, 1,  129.99), (13, 7, 1,   39.99),
    (14, 9, 1,  799.99),
    (15,10, 1,   79.98), (15,11, 5,  19.99),
    (16, 1, 1, 1999.99), (16,  3, 1, 249.99),
    (17,11, 5,   19.99), (17, 12, 2,  59.99),   (17, 15, 1, 69.99),
    (18,19, 1,   79.98), (18, 20, 1, 169.98),
    (19, 9, 1,  799.99), (19, 10, 1,  79.99),   (19,  3, 1, 249.99),
    (20,21, 1, 1249.98),
    (21, 6, 1,  129.99), (21,  7, 2,  39.99),   (21, 14, 1, 44.99),
    (22, 3, 1,  249.99),
    (23,24, 1,  799.99),
    (24, 2, 1,  999.99), (24, 12, 1,  59.99),   (24, 11, 1, 19.99),
    (25,11, 5,   19.99), (25, 12, 1,  59.99),
    (26, 6, 1,  129.99), (26,  7, 2,  39.99),   (26, 11, 3, 19.99),
    (27, 9, 1,  799.99),
    (28,10, 1,   79.99), (28, 14, 2,  44.99),   (28, 11, 4, 19.99),
    (29,12, 1,   59.99), (29, 11, 3,  19.99),   (29, 15, 1, 69.99);

-- Reviews
INSERT INTO reviews (product_id, customer_id, rating, body, created_at) VALUES
    (1, 1, 5, 'Best laptop I have ever used!',        '2024-01-15'),
    (1, 6, 4, 'Great performance, pricey but worth it', '2024-02-15'),
    (2, 3, 5, 'Incredible camera quality',            '2024-02-01'),
    (2, 10, 4, 'Love the new Dynamic Island',         '2024-03-20'),
    (3, 1, 5, 'Sound quality is exceptional',         '2024-01-20'),
    (4, 2, 5, 'Excellent recipes, very practical',    '2024-01-20'),
    (5, 2, 4, 'Changed how I write code',             '2024-01-30'),
    (6, 7, 3, 'Good shoes but sizing runs small',     '2024-03-01'),
    (9, 8, 5, 'Picture quality is stunning',          '2024-03-05'),
    (15, 9, 4, 'Great precision for gaming',          '2024-03-15');
