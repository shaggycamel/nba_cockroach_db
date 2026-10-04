-- The two id-minting functions, exactly as they exist in the database (pg_get_functiondef,
-- with a terminating semicolon added). Answers "where is generate_customer_id defined?" —
-- nowhere else: the database was its only source and this file is now the only copy outside it.
--
-- Both add the 'cus_' prefix themselves; the argument is the length of the random suffix.
-- They mint different shapes: generate_id draws from the full alphanumeric alphabet,
-- generate_customer_id from lowercase only with l and o removed.
--
-- Post-swap target is schema `fty`; during the fty_dev promotion, rewrite the CREATE lines
-- with: sed 's/FUNCTION fty\./FUNCTION fty_dev./'

CREATE OR REPLACE FUNCTION fty.generate_customer_id(p_id_length integer DEFAULT 12)
 RETURNS text
 LANGUAGE sql
AS $function$ WITH cfg AS (
    -- removed ambigious values and uppercase
    SELECT '0123456789abcdefghijkmnpqrstuvwxyz'::text AS alphabet
  )
SELECT 'cus_' || string_agg(
    substr(
      cfg.alphabet,
      (
        floor(random() * length(cfg.alphabet)::float) + 1
      )::int,
      1
    ),
    ''
  )
FROM cfg,
  generate_series(1, p_id_length);

$function$
;
CREATE OR REPLACE FUNCTION fty.generate_id(id_length integer DEFAULT 12)
 RETURNS text
 LANGUAGE plpgsql
AS $function$
DECLARE alphabet text := '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';

alphabet_len int := length(alphabet);

result text := '';

i int;

BEGIN FOR i IN 1..id_length LOOP result := result || substr(
  alphabet,
  (floor(random() * alphabet_len) + 1)::int,
  1
);

END LOOP;

RETURN 'cus_' || result;

END;

$function$
;
