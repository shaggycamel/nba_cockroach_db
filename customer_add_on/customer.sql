DROP TABLE IF EXISTS fty.customer;

CREATE TABLE fty.customer (
    customer_id text PRIMARY KEY CHECK (customer_id ~ '^cus_[0-9a-zA-Z]{12}$'),
    name text NOT NULL,
    email text,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

INSERT INTO fty.customer (customer_id, name, email)
VALUES (
        'cus_k3mZ9pX7Rq2w',
        'Oliver Eaton',
        'eat_fred@proton.me'
    );