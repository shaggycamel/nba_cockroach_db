CREATE OR REPLACE VIEW nba.nba_schedule_vw AS
SELECT home_away_union.season,
    home_away_union.season_type,
    home_away_union.game_id,
    home_away_union.game_date,
    home_away_union.matchup,
    home_away_union.team,
    home_away_union.home_away,
    regexp_replace(replace(home_away_union.matchup, home_away_union.team, ''::text), ' @ | vs. '::text, ''::text, 'gi'::text) AS against
   FROM ( SELECT league_game_schedule.season,
            league_game_schedule.season_type,
            league_game_schedule.game_id,
            league_game_schedule.game_date,
            league_game_schedule.matchup,
            "left"(league_game_schedule.matchup, 3) AS team,
                CASE
                    WHEN league_game_schedule.matchup ~~ '%vs%'::text THEN 'home'::text
                    ELSE 'away'::text
                END AS home_away
           FROM nba.league_game_schedule
        UNION ALL
         SELECT league_game_schedule.season,
            league_game_schedule.season_type,
            league_game_schedule.game_id,
            league_game_schedule.game_date,
            league_game_schedule.matchup,
            "right"(league_game_schedule.matchup, 3) AS team,
                CASE
                    WHEN league_game_schedule.matchup ~~ '%@%'::text THEN 'home'::text
                    ELSE 'away'::text
                END AS home_away
           FROM nba.league_game_schedule) home_away_union
  WHERE home_away_union.season_type = 'Regular Season'::text
  
 

