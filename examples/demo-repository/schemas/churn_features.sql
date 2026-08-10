CREATE TABLE churn_features (
    customer_id VARCHAR(64) NOT NULL,
    email_domain VARCHAR(320),
    churn_score NUMBER(10,6)
);
