-- Dumped from postgres with pg_get_viewdef (util.active_player_vw).
-- Until now this view existed only in the database; this file is its only copy.
create or replace view util.active_player_vw as
 SELECT DISTINCT ON (d.season, d.platform, d.source_id) d.season,
    d.platform,
    d.source_id,
    d.source_name,
    m.player_key,
    p.conformed_name
   FROM ((util.player_directory_vw d
     LEFT JOIN util.player_source_id m ON ((((m.platform)::text = d.platform) AND (m.source_id = d.source_id))))
     LEFT JOIN util.player p ON ((p.player_key = m.player_key)))
  ORDER BY d.season, d.platform, d.source_id, d.source_name;
