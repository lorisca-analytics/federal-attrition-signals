-- Clean tables for the analysis. Run by fas/build.py, which first creates two views:
--   raw_separations  every row of every current separations file, plus file_month
--   raw_employment   every row of every headcount snapshot, plus snapshot_month
-- Thresholds come in as the table `params` (one row).

-- 1. One row per separation, with the fields the analysis uses.
create or replace table separations as
select
    file_month,
    personnel_action_effective_date_yyyymm                          as effective_month,
    -- federal fiscal year runs Oct to Sep
    cast(substr(personnel_action_effective_date_yyyymm, 1, 4) as int)
      + case when cast(substr(personnel_action_effective_date_yyyymm, 5, 2) as int) >= 10 then 1 else 0 end
                                                                    as fiscal_year,
    agency_code,
    agency,
    coalesce(occupational_group, 'UNKNOWN')                         as occupational_group,
    separation_category_code                                        as category_code,
    case separation_category_code
        when 'SC' then 'quit'
        when 'SD' then 'retirement'
        when 'SG' then 'retirement'
        when 'SE' then 'early_out'
        when 'SH' then 'reduction_in_force'
        when 'SA' then 'transfer'
        when 'SB' then 'transfer'
        when 'SJ' then 'termination_or_expired'
        else 'other'
    end                                                             as reason,
    coalesce(drp_indicator, 'N')                                    as drp_indicator
from raw_separations
where personnel_action_effective_date_yyyymm >= (select first_month from params);

-- 2. Headcount per September snapshot (and the newest month).
create or replace table headcount as
select snapshot_month, agency_code, coalesce(occupational_group, 'UNKNOWN') as occupational_group,
       sum(cast("count" as int)) as headcount
from raw_employment
group by all;

-- Latest name for each agency code, so renamed agencies stay one line.
create or replace table agency_names as
select agency_code, arg_max(agency, file_month) as agency
from separations group by agency_code;

-- 3. Coverage check, per agency and file month.
-- A file month is a gap when an agency that normally reports reports far fewer
-- separations than its own recent median. Missing data must never look like retention.
create or replace table file_months as
select distinct file_month from separations;

create or replace table agency_file_counts as
with big as (   -- agencies large enough for the check to mean something
    select agency_code from headcount
    group by agency_code having max(headcount) >= (select min_headcount from params)
),
grid as (select b.agency_code, f.file_month from big b cross join file_months f),
counts as (select agency_code, file_month, count(*) as n from separations group by all)
select g.agency_code, g.file_month, coalesce(c.n, 0) as separations
from grid g left join counts c using (agency_code, file_month);

create or replace table coverage as
select
    agency_code,
    file_month,
    separations,
    median(separations) over (
        partition by agency_code order by file_month
        rows between 12 preceding and 1 preceding)                as baseline
from agency_file_counts;

create or replace table coverage as
select *,
    baseline is not null
      and baseline >= (select min_baseline from params)
      and separations < baseline * (select gap_ratio from params)  as is_gap,
    cast(substr(file_month, 1, 4) as int)
      + case when cast(substr(file_month, 5, 2) as int) >= 10 then 1 else 0 end as fiscal_year
from coverage;

-- An agency that really shrinks (headcount at the end of the year under half of the start)
-- reports few separations because few people are left. That is not a gap.
create or replace table shrinking as
select e.agency_code, e.fiscal_year
from (select cast(substr(snapshot_month, 1, 4) as int) as fiscal_year, agency_code, sum(headcount) as hc
      from headcount where substr(snapshot_month, 5, 2) = '09' group by all) e
join (select cast(substr(snapshot_month, 1, 4) as int) as fiscal_year, agency_code, sum(headcount) as hc
      from headcount where substr(snapshot_month, 5, 2) = '09' group by all) b
  on b.agency_code = e.agency_code and b.fiscal_year = e.fiscal_year - 1
where e.hc < b.hc * 0.5;

create or replace table coverage as
select c.* replace (c.is_gap and s.agency_code is null as is_gap)
from coverage c left join shrinking s using (agency_code, fiscal_year);

-- An agency-year is incomplete when any of its file months is a gap.
create or replace table agency_year_coverage as
select agency_code, fiscal_year, bool_or(is_gap) as incomplete,
       count(*) filter (where is_gap) as gap_months
from coverage group by all;

-- 4. Rates per 100 employees, by agency and fiscal year.
-- Denominator: average of the September headcount before and at the end of the year.
create or replace table hc_agency as
select cast(substr(snapshot_month, 1, 4) as int) + case when substr(snapshot_month, 5, 2) >= '10' then 1 else 0 end as fiscal_year,
       agency_code, sum(headcount) as headcount
from headcount where substr(snapshot_month, 5, 2) = '09' group by all;

create or replace table agency_year as
with s as (
    select agency_code, fiscal_year, reason, count(*) as n,
           count(*) filter (where drp_indicator = 'Y') as drp
    from separations group by all
),
piv as (
    select agency_code, fiscal_year,
        sum(n) filter (where reason = 'quit')                   as quits,
        sum(n) filter (where reason = 'retirement')             as retirements,
        sum(n) filter (where reason = 'early_out')              as early_outs,
        sum(n) filter (where reason = 'reduction_in_force')     as reductions_in_force,
        sum(n) filter (where reason = 'transfer')               as transfers,
        sum(n) filter (where reason = 'termination_or_expired') as terminations_or_expired,
        sum(n) filter (where reason = 'other')                  as other,
        sum(n)                                                  as separations,
        sum(drp)                                                as drp_separations,
        sum(drp) filter (where reason = 'quit')                 as drp_quits
    from s group by all
),
den as (
    select e.agency_code, e.fiscal_year,
           b.headcount as start_headcount, e.headcount as end_headcount,
           (e.headcount + b.headcount) / 2.0 as avg_headcount
    from hc_agency e join hc_agency b
      on b.agency_code = e.agency_code and b.fiscal_year = e.fiscal_year - 1
)
select
    p.fiscal_year,
    p.agency_code,
    n.agency,
    d.start_headcount::int                                        as start_headcount,
    d.end_headcount::int                                          as end_headcount,
    round(d.avg_headcount)::int                                   as avg_headcount,
    coalesce(p.separations, 0)                                    as separations,
    coalesce(p.quits, 0)                                          as quits,
    coalesce(p.retirements, 0)                                    as retirements,
    coalesce(p.early_outs, 0)                                     as early_outs,
    coalesce(p.reductions_in_force, 0)                            as reductions_in_force,
    coalesce(p.transfers, 0)                                      as transfers,
    coalesce(p.terminations_or_expired, 0)                        as terminations_or_expired,
    coalesce(p.other, 0)                                          as other,
    coalesce(p.drp_separations, 0)                                as drp_separations,
    coalesce(p.drp_quits, 0)                                      as drp_quits,
    round(100.0 * coalesce(p.quits, 0) / d.avg_headcount, 2)       as quit_rate,
    round(100.0 * (coalesce(p.quits, 0) - coalesce(p.drp_quits, 0)) / d.avg_headcount, 2) as quit_rate_excl_drp,
    round(100.0 * coalesce(p.separations, 0) / d.avg_headcount, 2) as separation_rate,
    coalesce(c.incomplete, false)                                 as incomplete,
    coalesce(c.gap_months, 0)                                     as gap_months,
    p.fiscal_year >= (select provisional_from_fy from params)     as provisional
from piv p
join den d using (agency_code, fiscal_year)
join agency_names n using (agency_code)
left join agency_year_coverage c using (agency_code, fiscal_year)
where d.avg_headcount >= (select min_headcount from params);

-- 5. Rates by occupational group, government wide, leaving out agency-years that fail coverage.
create or replace table hc_occ as
select cast(substr(snapshot_month, 1, 4) as int) as fiscal_year, agency_code, occupational_group, headcount
from headcount where substr(snapshot_month, 5, 2) = '09';

create or replace table occupation_year as
with ok as (
    select agency_code, fiscal_year from agency_year where not incomplete
),
s as (
    select s.fiscal_year, s.occupational_group, count(*) filter (where reason = 'quit') as quits,
           count(*) filter (where reason = 'quit' and drp_indicator = 'Y') as drp_quits, count(*) as separations
    from separations s join ok using (agency_code, fiscal_year)
    group by all
),
d as (
    select e.fiscal_year, e.occupational_group, sum((e.headcount + coalesce(b.headcount, e.headcount)) / 2.0) as avg_headcount
    from hc_occ e
    join ok on ok.agency_code = e.agency_code and ok.fiscal_year = e.fiscal_year
    left join hc_occ b on b.agency_code = e.agency_code and b.occupational_group = e.occupational_group
                      and b.fiscal_year = e.fiscal_year - 1
    group by all
)
select s.fiscal_year, s.occupational_group,
       round(d.avg_headcount)::int as avg_headcount,
       s.separations, s.quits, s.drp_quits,
       round(100.0 * s.quits / d.avg_headcount, 2)       as quit_rate,
       round(100.0 * (s.quits - s.drp_quits) / d.avg_headcount, 2) as quit_rate_excl_drp,
       round(100.0 * s.separations / d.avg_headcount, 2) as separation_rate,
       s.fiscal_year >= (select provisional_from_fy from params) as provisional
from s join d using (fiscal_year, occupational_group)
where d.avg_headcount >= (select min_headcount from params)
  and s.occupational_group <> 'UNKNOWN';

-- 6. Federal (OPM, covered agencies only) vs BLS industries, per fiscal year.
-- BLS rates are monthly, per 100 employees. Twelve months added up give a yearly rate.
create or replace table benchmark_year as
with opm as (
    select fiscal_year, 'Federal civilian (OPM, covered agencies)' as series,
           round(100.0 * sum(quits) / sum(avg_headcount), 2) as quit_rate,
           count(*) as months_or_agencies
    from agency_year where not incomplete group by fiscal_year
    union all
    select fiscal_year, 'Federal civilian (OPM), quits without DRP' as series,
           round(100.0 * sum(quits - drp_quits) / sum(avg_headcount), 2) as quit_rate,
           count(*) as months_or_agencies
    from agency_year where not incomplete and fiscal_year >= 2025 group by fiscal_year
),
bls as (
    select year + case when month >= 10 then 1 else 0 end as fiscal_year,
           industry || ' (BLS)' as series,
           round(sum(rate), 2) as quit_rate,
           count(*) as months_or_agencies
    from jolts where measure = 'quits' group by all
    having count(*) = 12
)
select fiscal_year, series, quit_rate, fiscal_year >= (select provisional_from_fy from params) as provisional
from (select * from opm union all select * from bls)
where fiscal_year >= (select min(fiscal_year) from agency_year);

-- 7. Why people left, government wide, per fiscal year. Covered agency-years only.
-- DRP-flagged exits get their own segment so they are not read as ordinary quits or retirements.
create or replace table reason_year as
with ok as (select agency_code, fiscal_year, avg_headcount from agency_year where not incomplete),
seg as (
    select s.fiscal_year,
        case
            when s.drp_indicator = 'Y' then 'DRP-flagged exit'
            when s.reason = 'quit' then 'Quit'
            when s.reason in ('retirement', 'early_out') then 'Retirement or early out'
            when s.reason = 'reduction_in_force' then 'Reduction in force'
            else 'Transfer, termination or other'
        end as segment,
        count(*) as separations
    from separations s join ok using (agency_code, fiscal_year)
    group by all
),
den as (select fiscal_year, sum(avg_headcount) as hc from ok group by all)
select seg.fiscal_year, seg.segment, seg.separations,
       round(100.0 * seg.separations / den.hc, 2) as rate,
       seg.fiscal_year >= (select provisional_from_fy from params) as provisional
from seg join den using (fiscal_year);
