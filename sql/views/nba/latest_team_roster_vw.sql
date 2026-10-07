-- RETIRED 2026-10-07: this view was dropped from both cockroach and postgres. Nothing
-- consumes it: nba.shiny reads nba.team_roster_vw, nba.shiny.draft reads no roster view at
-- all, and a grep of every repo under ~/git finds no other reference.
-- This file is kept only as the surviving record of the definition -- DELETE IT if the view
-- proves not to be useful.
-- Caveat while it is here: scripts/apply_views.py globs sql/views/*/*.sql, so any run of it
-- re-creates the view this file was retired to remove. Move it out of that glob (or delete
-- it) before the next apply.

create or replace view nba.latest_team_roster_vw as

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
                     LEFT JOIN util.player_id_map_vw nm ON tr.player_id = nm.nba_id::double precision) inner_q
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
     LEFT JOIN util.player_id_map_vw id_match ON cte_latest_team_roster.player_id = id_match.nba_id::double precision
