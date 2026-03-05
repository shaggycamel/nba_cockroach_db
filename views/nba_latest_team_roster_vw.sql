WITH cte_latest_team_roster AS (
         SELECT inner_q.season,
            inner_q.team_slug,
            inner_q.team_id,
            inner_q.player,
            inner_q.salary,
            inner_q.num,
            inner_q."position",
            inner_q.player_id,
            inner_q.how_acquired,
            inner_q.rn
           FROM ( SELECT tr.season,
                    tr.team_slug,
                    tr.team_id,
                    nm.nba_name AS player,
                    tr.salary,
                    tr.num,
                    tr."position",
                    tr.player_id,
                    tr.how_acquired,
                    tr.entry_date,
                    tr.exit_date,
                    row_number() OVER (PARTITION BY tr.season, tr.player_id ORDER BY tr.entry_date DESC) AS rn
                   FROM nba.team_roster tr
                     LEFT JOIN util.nba_fty_name_match nm ON tr.player_id = nm.nba_id::double precision) inner_q
          WHERE inner_q.rn = 1
        )
 SELECT cte_latest_team_roster.season,
    cte_latest_team_roster.team_slug,
    cte_latest_team_roster.team_id,
    cte_latest_team_roster.player,
    cte_latest_team_roster.salary,
    cte_latest_team_roster.num,
    cte_latest_team_roster."position",
    cte_latest_team_roster.player_id,
    id_match.espn_id,
    id_match.yahoo_id,
    cte_latest_team_roster.how_acquired
   FROM cte_latest_team_roster
     LEFT JOIN util.nba_fty_name_match id_match ON cte_latest_team_roster.player_id = id_match.nba_id::double precision;