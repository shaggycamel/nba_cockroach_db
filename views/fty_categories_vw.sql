CREATE OR REPLACE VIEW fty.fty_categories_vw AS

SELECT fty_cat.platform,
    fty_cat.season,
    fty_cat.league_id,
    label.nba_category,
    label.fty_category,
    label.fmt_category,
    label.display_order,
        CASE
	        WHEN fty_cat.category = 'FTM' THEN FALSE
	        WHEN fty_cat.category = 'FTA' THEN FALSE
	        WHEN fty_cat.category = 'FGM' THEN FALSE
	        WHEN fty_cat.category = 'FGA' THEN FALSE
            WHEN fty_cat.category IS NOT NULL THEN true
            ELSE false
        END AS h2h_cat
   FROM fty.category_label label
     LEFT JOIN fty.league_categories fty_cat ON label.fty_category = fty_cat.category::text;