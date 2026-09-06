"""Explicit SQLite schema for the inspected Olist CSV files."""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS geolocation;
DROP TABLE IF EXISTS product_category_name_translation;

CREATE TABLE customers (
	customer_id TEXT PRIMARY KEY,
	customer_unique_id TEXT NOT NULL,
	customer_zip_code_prefix INTEGER NOT NULL,
	customer_city TEXT NOT NULL,
	customer_state TEXT NOT NULL
);
CREATE TABLE geolocation (
	geolocation_id INTEGER PRIMARY KEY,
	geolocation_zip_code_prefix INTEGER NOT NULL,
	geolocation_lat REAL,
	geolocation_lng REAL,
	geolocation_city TEXT,
	geolocation_state TEXT
);
CREATE TABLE sellers (
	seller_id TEXT PRIMARY KEY,
	seller_zip_code_prefix INTEGER NOT NULL,
	seller_city TEXT NOT NULL,
	seller_state TEXT NOT NULL
);
CREATE TABLE orders (
	order_id TEXT PRIMARY KEY,
	customer_id TEXT NOT NULL REFERENCES customers(customer_id),
	order_status TEXT NOT NULL,
	order_purchase_timestamp TEXT NOT NULL,
	order_approved_at TEXT,
	order_delivered_carrier_date TEXT,
	order_delivered_customer_date TEXT,
	order_estimated_delivery_date TEXT NOT NULL
);
CREATE TABLE products (
	product_id TEXT PRIMARY KEY,
	product_category_name TEXT,
	product_name_lenght REAL,
	product_description_lenght REAL,
	product_photos_qty REAL,
	product_weight_g REAL,
	product_length_cm REAL,
	product_height_cm REAL,
	product_width_cm REAL
);
CREATE TABLE product_category_name_translation (
	product_category_name TEXT PRIMARY KEY,
	product_category_name_english TEXT NOT NULL
);
CREATE TABLE order_items (
	order_id TEXT NOT NULL REFERENCES orders(order_id),
	order_item_id INTEGER NOT NULL,
	product_id TEXT NOT NULL REFERENCES products(product_id),
	seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
	shipping_limit_date TEXT NOT NULL,
	price REAL NOT NULL,
	freight_value REAL NOT NULL,
	PRIMARY KEY (order_id, order_item_id)
);
CREATE TABLE order_payments (
	order_id TEXT NOT NULL REFERENCES orders(order_id),
	payment_sequential INTEGER NOT NULL,
	payment_type TEXT NOT NULL,
	payment_installments INTEGER NOT NULL,
	payment_value REAL NOT NULL,
	PRIMARY KEY (order_id, payment_sequential)
);
CREATE TABLE order_reviews (
	review_row_id INTEGER PRIMARY KEY,
	review_id TEXT NOT NULL,
	order_id TEXT NOT NULL REFERENCES orders(order_id),
	review_score INTEGER NOT NULL,
	review_comment_title TEXT,
	review_comment_message TEXT,
	review_creation_date TEXT NOT NULL,
	review_answer_timestamp TEXT NOT NULL
);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_purchase_timestamp ON orders(order_purchase_timestamp);
CREATE INDEX idx_orders_status ON orders(order_status);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_order_items_seller_id ON order_items(seller_id);
CREATE INDEX idx_order_payments_order_id ON order_payments(order_id);
CREATE INDEX idx_order_reviews_order_id ON order_reviews(order_id);
CREATE INDEX idx_products_category ON products(product_category_name);
CREATE INDEX idx_sellers_zip ON sellers(seller_zip_code_prefix);
CREATE INDEX idx_customers_unique_id ON customers(customer_unique_id);
CREATE INDEX idx_customers_zip ON customers(customer_zip_code_prefix);
CREATE INDEX idx_geolocation_zip ON geolocation(geolocation_zip_code_prefix);

CREATE TABLE IF NOT EXISTS dashboard_items (
	 id TEXT PRIMARY KEY,
	 question TEXT NOT NULL,
	 agent_mode TEXT,
	 query_snapshot TEXT NOT NULL,
	 chart_snapshot TEXT NOT NULL,
	 result_snapshot TEXT NOT NULL,
	 insight TEXT,
	 created_at TEXT NOT NULL,
	 updated_at TEXT NOT NULL
);
"""

REQUIRED_TABLES = (
	"customers", "geolocation", "orders", "order_items", "order_payments",
	"order_reviews", "products", "sellers", "product_category_name_translation",
)
