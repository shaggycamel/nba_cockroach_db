create or replace view nba.team_roster_vw as

-- Player naming and cross platform ids come from util.player_id_map_vw, replacing
-- util.conformed_player_id_RETIRED. nba.team_roster.player_id is double precision,
-- hence the cast on the join.

SELECT tr.season,
    tr.team_id,
    tr.team_slug,
    tr.player_id,
    nm.espn_id,
    nm.yahoo_id,
    nm.conformed_name AS player_name,
    tr."position",
    tr.how_acquired,
    tr.salary,
    COALESCE(tr.entry_date, kd.begin_date) AS entry_date,
    COALESCE(tr.exit_date, kd.end_date) AS exit_date
   FROM nba.team_roster tr
     LEFT JOIN util.player_id_map_vw nm ON tr.player_id = nm.nba_id::double precision
     LEFT JOIN ( SELECT key_dates.season,
            key_dates.season_type,
            key_dates.begin_date,
            key_dates.end_date
           FROM nba.key_dates
          WHERE key_dates.season_type = 'Regular Season'::text) kd ON tr.season = kd.season
