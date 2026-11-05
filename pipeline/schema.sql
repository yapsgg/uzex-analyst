-- Rebuilt from scratch on every load. Only the `market` schema is touched.
DROP SCHEMA IF EXISTS market CASCADE;
CREATE SCHEMA market;
SET search_path = market;

CREATE TABLE regions (
  region_uz text PRIMARY KEY, region_ru text NOT NULL UNIQUE, region_en text NOT NULL UNIQUE
);
CREATE TABLE products (
  product text PRIMARY KEY, product_en text NOT NULL, product_uz text NOT NULL,
  aliases text NOT NULL, hs_code text NOT NULL, category text NOT NULL, industry text NOT NULL
);
CREATE TABLE companies (
  inn text PRIMARY KEY, name text NOT NULL, search_key text NOT NULL,
  region_uz text NOT NULL REFERENCES regions, activity text NOT NULL,
  role text NOT NULL CHECK (role IN ('seller', 'buyer')), vat_payer boolean NOT NULL
);
CREATE TABLE brokers (
  broker_code text PRIMARY KEY, name text NOT NULL, search_key text NOT NULL, inn text NOT NULL,
  region_uz text NOT NULL REFERENCES regions
);
CREATE TABLE contracts (
  contract_no integer PRIMARY KEY, product text NOT NULL REFERENCES products, raw_name text NOT NULL,
  grade text, class text, brand text, product_type text, size text, hs_code text NOT NULL,
  goods_group text NOT NULL, unit text NOT NULL, lot_size integer NOT NULL,
  currency text NOT NULL CHECK (currency IN ('UZS', 'USD')), base_price numeric NOT NULL,
  deposit_pct integer NOT NULL, delivery_basis text NOT NULL, region_uz text NOT NULL REFERENCES regions,
  warehouse_address text NOT NULL, auction_type text NOT NULL, contract_type text NOT NULL,
  contract_form text NOT NULL, payment_term_days integer NOT NULL,
  delivery_term_days integer NOT NULL, packaging text NOT NULL,
  seller_inn text NOT NULL REFERENCES companies, registered_on date NOT NULL, valid_until date NOT NULL
);
CREATE TABLE fx_rates (rate_date date PRIMARY KEY, uzs_per_usd numeric NOT NULL);
CREATE TABLE deals (
  deal_no integer PRIMARY KEY, deal_date date NOT NULL REFERENCES fx_rates, deal_time time NOT NULL,
  contract_no integer NOT NULL REFERENCES contracts, buyer_inn text NOT NULL REFERENCES companies,
  seller_broker text NOT NULL REFERENCES brokers, buyer_broker text NOT NULL REFERENCES brokers,
  quantity_lots bigint NOT NULL, amount numeric NOT NULL, start_price numeric NOT NULL,
  status text NOT NULL, payment_date date, delivery_date date, delivered_lots bigint
);
CREATE INDEX ON deals (deal_date);
CREATE INDEX ON deals (contract_no);
CREATE INDEX ON deals (buyer_inn);
CREATE INDEX ON contracts (product);
CREATE INDEX ON contracts (seller_inn);

-- The agent reads only these views. Every business rule from the README lives here.
-- build.py derives v_deals from this view: valid deals only, with no is_valid column.
CREATE VIEW v_all_deals AS
SELECT
  d.deal_no, d.deal_date, d.deal_time, EXTRACT(YEAR FROM d.deal_date)::int AS deal_year,
  d.contract_no, c.product, p.product_en, c.raw_name, c.hs_code, p.category, p.industry,
  c.goods_group, c.grade, c.class, c.brand, c.product_type, c.size,
  c.auction_type, c.contract_type, c.contract_form, c.delivery_basis, c.packaging,
  c.region_uz, r.region_ru, r.region_en,
  c.seller_inn, se.name AS seller_name, d.buyer_inn, bu.name AS buyer_name,
  d.seller_broker, d.buyer_broker,
  d.status, d.status <> 'cancelled' AS is_valid,
  c.unit, c.lot_size, d.quantity_lots,
  d.quantity_lots * c.lot_size AS volume,
  CASE c.unit WHEN 'тонна' THEN d.quantity_lots * c.lot_size::numeric
              WHEN 'килограмм' THEN d.quantity_lots * c.lot_size / 1000.0 END AS volume_tonnes,
  c.currency, d.amount, fx.uzs_per_usd AS fx_rate,
  CASE c.currency WHEN 'USD' THEN d.amount * fx.uzs_per_usd ELSE d.amount END AS amount_uzs,
  CASE c.currency WHEN 'USD' THEN d.amount ELSE d.amount / fx.uzs_per_usd END AS amount_usd,
  d.amount / (d.quantity_lots * c.lot_size) AS unit_price,
  d.start_price, c.base_price,
  d.payment_date, d.delivery_date, d.delivered_lots,
  d.delivered_lots * c.lot_size AS delivered_volume,
  d.delivered_lots::numeric / d.quantity_lots
    * CASE c.currency WHEN 'USD' THEN d.amount * fx.uzs_per_usd ELSE d.amount END
    AS delivered_amount_uzs,
  c.deposit_pct, c.payment_term_days, c.delivery_term_days,
  d.payment_date - d.deal_date AS days_to_payment,
  d.delivery_date - d.payment_date AS days_to_delivery,
  d.delivery_date - d.payment_date > c.delivery_term_days AS is_late_delivery
FROM deals d
JOIN contracts c USING (contract_no)
JOIN products p ON p.product = c.product
JOIN regions r ON r.region_uz = c.region_uz
JOIN companies se ON se.inn = c.seller_inn
JOIN companies bu ON bu.inn = d.buyer_inn
JOIN fx_rates fx ON fx.rate_date = d.deal_date;

CREATE VIEW v_contracts AS
SELECT c.*, p.product_en, p.category, p.industry, se.name AS seller_name
FROM contracts c JOIN products p USING (product) JOIN companies se ON se.inn = c.seller_inn;

CREATE VIEW v_companies AS
SELECT co.inn, co.name, co.region_uz, r.region_ru, r.region_en, co.activity, co.role, co.vat_payer
FROM companies co JOIN regions r USING (region_uz);

CREATE VIEW v_brokers AS
SELECT b.broker_code, b.name, b.inn, b.region_uz, r.region_ru, r.region_en
FROM brokers b JOIN regions r USING (region_uz);

CREATE VIEW v_products AS SELECT product, product_en, product_uz, hs_code, category, industry FROM products;
CREATE VIEW v_fx_rates AS SELECT rate_date, uzs_per_usd FROM fx_rates;
CREATE VIEW v_regions AS SELECT region_uz, region_ru, region_en FROM regions;
