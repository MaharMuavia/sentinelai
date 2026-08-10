CREATE TABLE raw_customers (
    customer_id VARCHAR(64) NOT NULL,
    email VARCHAR(320),
    country VARCHAR(2),
    created_at TIMESTAMP_NTZ NOT NULL
);
