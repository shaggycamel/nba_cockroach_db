CREATE OR REPLACE VIEW nba.nba_player_box_score_vw AS
SELECT lgs.season,
    lgs.season_type,
    ("right"(lgs.season, 2) || '-'::text) || lgs.season_type AS year_season_type,
    pbs.game_id,
    lgs.game_date,
    id_match.nba_name AS player_name,
    pbs.player_id,
    id_match.espn_id,
    id_match.yahoo_id,
    team.team_slug,
    pbs.team_abbreviation AS team_slug_base,
    pbs.min,
    pbs.fgm,
    pbs.fga,
    pbs.fg_pct,
    pbs.fg3_m,
    pbs.fg3_a,
    pbs.fg3_pct,
    pbs.ftm,
    pbs.fta,
    pbs.ft_pct,
    pbs.pts,
    pbs.oreb,
    pbs.dreb,
    pbs.reb,
    pbs.ast,
    pbs.stl,
    pbs.blk,
    pbs.tov,
    pbs.pf,
        CASE
            WHEN (
            CASE
                WHEN pbs.pts >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.reb >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.ast >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.stl >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.blk >= 10::double precision THEN 1
                ELSE 0
            END) >= 2 THEN 1
            ELSE 0
        END AS dd2,
        CASE
            WHEN (
            CASE
                WHEN pbs.pts >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.reb >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.ast >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.stl >= 10::double precision THEN 1
                ELSE 0
            END +
            CASE
                WHEN pbs.blk >= 10::double precision THEN 1
                ELSE 0
            END) >= 3 THEN 1
            ELSE 0
        END AS td3,
    pbs.plus_minus,
    pbs.e_off_rating,
    pbs.off_rating,
    pbs.e_def_rating,
    pbs.def_rating,
    pbs.e_net_rating,
    pbs.net_rating,
    pbs.ast_pct,
    pbs.ast_tov,
    pbs.ast_ratio,
    pbs.oreb_pct,
    pbs.dreb_pct,
    pbs.reb_pct,
    pbs.tm_tov_pct,
    pbs.efg_pct,
    pbs.ts_pct,
    pbs.usg_pct,
    pbs.e_usg_pct,
    pbs.e_pace,
    pbs.pace,
    pbs.pace_per40,
    pbs.poss,
    pbs.pie
   FROM nba.player_box_score pbs
     LEFT JOIN ( SELECT DISTINCT league_game_schedule.season,
            league_game_schedule.season_type,
            league_game_schedule.game_date,
            league_game_schedule.game_id
           FROM nba.league_game_schedule) lgs ON pbs.game_id::double precision = lgs.game_id::double precision
     LEFT JOIN util.nba_fty_name_match id_match ON pbs.player_id = id_match.nba_id
     LEFT JOIN nba.nba_latest_team_roster_vw team ON pbs.player_id::double precision = team.player_id AND lgs.season = team.season
  WHERE lgs.season_type <> 'All Star'::text;