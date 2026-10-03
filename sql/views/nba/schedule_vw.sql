create or replace view nba.schedule_vw as

 SELECT lgs.season_type,
    lgs.season,
    lgs.game_id,
    lgs.game_date,
    lgs.matchup,
    lgs.team,
    lgs.opponent,
    lgs.home,
    lgs.team_winner,
    lgs.team_loser
   FROM nba.league_game_schedule lgs
     JOIN ( SELECT teams.team_slug
           FROM nba.teams) relevant_teams ON lgs.team = relevant_teams.team_slug
