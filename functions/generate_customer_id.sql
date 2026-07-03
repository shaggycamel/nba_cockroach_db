CREATE OR REPLACE FUNCTION fty.generate_id(id_length int DEFAULT 12) RETURNS text LANGUAGE plpgsql AS $$
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

$$;