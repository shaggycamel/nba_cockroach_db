CREATE OR REPLACE VIEW nba.nba_player_box_score_vw AS
SELECT
	lgs.season,
    lgs.season_type,
    lgs.game_id,
    lgs.game_date,
    lgs.team,
    lgs.opponent,
    lgs.home,
    tr.player_id,
    nm.espn_id,
    nm.yahoo_id,
    nm.nba_name AS player_name,
    COALESCE(inj.reason, pbs.comment) AS inj_reason,
    inj.status AS inj_status,
    pbs.min,
    pbs.pts,
    pbs.fg3_m,
    pbs.fgm,
    pbs.fga,
    pbs.ftm,
    pbs.fta,
    pbs.ast,
    pbs.reb,
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
        END AS td3
   FROM nba.league_game_schedule lgs
     LEFT JOIN ( SELECT tr_inr.season,
            tr_inr.team_slug,
            tr_inr.player_id,
            tr_inr.player,
            COALESCE(tr_inr.entry_date, kd.begin_date) AS entry_date,
            COALESCE(tr_inr.exit_date, kd.end_date) AS exit_date
           FROM nba.team_roster tr_inr
             LEFT JOIN ( SELECT key_dates.season,
                    key_dates.season_type,
                    key_dates.begin_date,
                    key_dates.end_date
                   FROM nba.key_dates
                  WHERE key_dates.season_type = 'Regular Season'::text) kd ON tr_inr.season = kd.season) tr ON lgs.season = tr.season AND lgs.team = tr.team_slug AND lgs.game_date >= tr.entry_date AND lgs.game_date < tr.exit_date
     -- need game_date in join to stop duplication
     LEFT JOIN nba.injuries inj ON lgs.game_id = inj.game_id AND lgs.game_date = inj.game_date AND tr.player_id = inj.nba_id
     LEFT JOIN nba.player_box_score pbs ON lgs.game_id = pbs.game_id AND tr.player_id = pbs.player_id::double precision
     LEFT JOIN util.nba_fty_name_match AS nm ON tr.player_id = nm.nba_id

