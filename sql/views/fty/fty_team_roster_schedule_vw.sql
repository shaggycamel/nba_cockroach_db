CREATE OR REPLACE VIEW fty.fty_team_roster_schedule_vw AS

SELECT roster.season,
    roster.platform,
    roster.league_id,
    roster.assigned_date,
    roster.matchup_period,
    schedule_dates.matchup_start,
    schedule_dates.matchup_end,
    roster.competitor_id,
    competitor.competitor_name,
    roster.player_fantasy_id,
    id_match.nba_id AS player_id,
    id_match.conformed_name AS player_name,
    roster.player_team,
    roster.player_injury_status,
    roster.player_acquisition_type,
    schedule.opponent_id,
    opponent.competitor_name AS opponent_name
   FROM fty.competitor_roster roster
     LEFT JOIN fty.league_matchup schedule ON roster.season = schedule.season AND roster.platform = schedule.platform AND roster.league_id = schedule.league_id AND roster.competitor_id = schedule.competitor_id AND roster.matchup_period = schedule.matchup_period
     LEFT JOIN fty.league_matchup_dates schedule_dates ON roster.season = schedule_dates.season AND roster.platform = schedule_dates.platform AND roster.league_id = schedule_dates.league_id AND roster.matchup_period = schedule_dates.matchup_period
     LEFT JOIN fty.league_competitor competitor ON roster.season = competitor.season AND roster.platform = competitor.platform AND roster.league_id = competitor.league_id AND roster.competitor_id = competitor.competitor_id
     LEFT JOIN fty.league_competitor opponent ON roster.season = opponent.season AND roster.platform = opponent.platform AND roster.league_id = opponent.league_id AND schedule.opponent_id = opponent.competitor_id::double precision
     LEFT JOIN ( SELECT nba_id,
            conformed_name,
            'Yahoo'::text AS platform,
            yahoo_id AS player_fantasy_id
           FROM util.conformed_player_id
        UNION ALL
         SELECT nba_id,
            conformed_name,
            'ESPN'::text AS platform,
            espn_id AS player_fantasy_id
           FROM util.conformed_player_id) id_match ON roster.platform = id_match.platform AND roster.player_fantasy_id::double precision = id_match.player_fantasy_id;