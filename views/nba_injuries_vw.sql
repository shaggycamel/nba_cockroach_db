create or replace view nba.nba_injuries_vw as

SELECT kd.season,
    kd.season_type,
    inj.game_date,
    inj.game_id,
    inj.matchup,
    inj.team,
    inj.team_slug,
    nm.conformed_name AS player_name,
    inj.nba_id,
    inj.status,
    inj.reason
   FROM nba.injuries inj
     LEFT JOIN nba.key_dates kd ON inj.game_date >= kd.begin_date AND inj.game_date <= kd.end_date
     LEFT JOIN util.conformed_player_id nm ON inj.nba_id = nm.nba_id::double precision;