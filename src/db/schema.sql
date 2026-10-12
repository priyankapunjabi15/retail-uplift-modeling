/*
==========================================================
  Hillstrom Uplift — Normalized Schema (T-SQL / SQL Server)
==========================================================

WHY NORMALIZE?
--------------
The raw CSV has everything in one flat table (64,000 rows × 17 cols).
That works for ML, but in a real production database you'd never
store customer attributes, campaign assignments, and outcome metrics
in one table. Why not?

  1. Redundancy — if a customer appears in multiple campaigns,
     their demographics get duplicated across rows.
  2. Update anomalies — change a customer's zip_code in one row
     but forget another → inconsistent data.
  3. Semantic clarity — "who is the customer" vs "what campaign
     were they in" vs "what did they do" are three different
     questions.

We split into 3 tables:

  customers            — who they are  (demographics + RFM)
  campaign_assignments — what group    (treatment vs control)
  outcomes             — what happened (visit, conversion, spend)

Linked by customer_id (primary key → foreign key).

This also lets us practice JOINs, which is the whole point of
Phase 3 from a portfolio perspective.

T-SQL DIFFERENCES FROM MySQL
-----------------------------
  MySQL                    SQL Server
  ─────                    ──────────
  AUTO_INCREMENT           IDENTITY(1,1)
  TINYINT(1)               BIT
  VARCHAR                  NVARCHAR  (Unicode-safe)
  ENGINE=InnoDB             (not needed — always transactional)
  LIMIT 10                 TOP 10
  IF NOT EXISTS (table)    check OBJECT_ID() IS NULL
*/

-- ── Use the target database ──────────────────────────
-- The loader creates the database first, then runs this script.
-- If running manually in SSMS, uncomment the next line:
-- USE hillstrom_uplift;
-- GO

-- ══════════════════════════════════════════════════════
-- TABLE 1: customers
-- ══════════════════════════════════════════════════════
-- One row per customer. Contains demographics and
-- RFM (Recency-Frequency-Monetary) features.
--
-- Columns:
--   customer_id       — surrogate key (auto-generated)
--   recency           — months since last purchase
--   history           — dollar value of past purchases
--   mens              — 1 if bought men's merchandise
--   womens            — 1 if bought women's merchandise
--   zip_code          — ordinal: 0=Rural, 1=Suburban, 2=Urban
--   newbie            — 1 if new customer (< 12 months)
--   channel_multichannel — 1 if purchased via multiple channels
--   channel_phone     — 1 if purchased via phone
--   channel_web       — 1 if purchased via web
--   history_segment_code — ordinal tier 0-6 from $0–$100 to $1000+
--   category_count    — number of categories purchased (mens+womens)
--   recency_bin       — quartile bin 0-3
--   history_bin       — quartile bin 0-3
-- ══════════════════════════════════════════════════════

IF OBJECT_ID('dbo.outcomes', 'U') IS NOT NULL
    DROP TABLE dbo.outcomes;
IF OBJECT_ID('dbo.campaign_assignments', 'U') IS NOT NULL
    DROP TABLE dbo.campaign_assignments;
IF OBJECT_ID('dbo.customers', 'U') IS NOT NULL
    DROP TABLE dbo.customers;
GO

CREATE TABLE dbo.customers (
    customer_id             INT IDENTITY(1,1) PRIMARY KEY,
    recency                 INT           NOT NULL,
    history                 FLOAT         NOT NULL DEFAULT 0,
    mens                    BIT           NOT NULL DEFAULT 0,
    womens                  BIT           NOT NULL DEFAULT 0,
    zip_code                SMALLINT      NOT NULL DEFAULT 0,
    newbie                  BIT           NOT NULL DEFAULT 0,
    channel_multichannel    BIT           NOT NULL DEFAULT 0,
    channel_phone           BIT           NOT NULL DEFAULT 0,
    channel_web             BIT           NOT NULL DEFAULT 0,
    history_segment_code    TINYINT       NOT NULL DEFAULT 0,
    category_count          TINYINT       NOT NULL DEFAULT 0,
    recency_bin             TINYINT       NOT NULL DEFAULT 0,
    history_bin             TINYINT       NOT NULL DEFAULT 0
);
GO


-- ══════════════════════════════════════════════════════
-- TABLE 2: campaign_assignments
-- ══════════════════════════════════════════════════════
-- Links each customer to their experimental group.
--
-- Columns:
--   assignment_id — surrogate key
--   customer_id   — FK → customers
--   segment       — original label: 'Mens E-Mail', 'Womens E-Mail', 'No E-Mail'
--   treatment     — binary: 1 = received email, 0 = control
--
-- WHY SEPARATE?
-- In a real system, one customer could be in many campaigns
-- over time. Separating assignments from demographics keeps
-- the schema extensible.
-- ══════════════════════════════════════════════════════

CREATE TABLE dbo.campaign_assignments (
    assignment_id   INT IDENTITY(1,1) PRIMARY KEY,
    customer_id     INT           NOT NULL,
    segment         NVARCHAR(50)  NOT NULL,
    treatment       BIT           NOT NULL DEFAULT 0,
    CONSTRAINT FK_assignments_customer
        FOREIGN KEY (customer_id) REFERENCES dbo.customers(customer_id)
);
GO


-- ══════════════════════════════════════════════════════
-- TABLE 3: outcomes
-- ══════════════════════════════════════════════════════
-- What happened after the campaign was sent.
--
-- Columns:
--   outcome_id  — surrogate key
--   customer_id — FK → customers
--   visit       — 1 if visited the site within 2 weeks
--   conversion  — 1 if made a purchase within 2 weeks
--   spend       — dollar amount spent (0.0 if no purchase)
--
-- WHY SEPARATE?
-- Outcomes are the "response variables" — they depend on
-- the campaign. Keeping them apart makes it easy to add
-- new outcome windows (e.g., 30-day spend) without
-- touching the customer table.
-- ══════════════════════════════════════════════════════

CREATE TABLE dbo.outcomes (
    outcome_id   INT IDENTITY(1,1) PRIMARY KEY,
    customer_id  INT    NOT NULL,
    visit        BIT    NOT NULL DEFAULT 0,
    conversion   BIT    NOT NULL DEFAULT 0,
    spend        FLOAT  NOT NULL DEFAULT 0,
    CONSTRAINT FK_outcomes_customer
        FOREIGN KEY (customer_id) REFERENCES dbo.customers(customer_id)
);
GO


-- ══════════════════════════════════════════════════════
-- INDEXES for faster JOINs and WHERE filters
-- ══════════════════════════════════════════════════════
-- Without indexes, every JOIN does a full table scan.
-- These cover the foreign keys and common filter columns.

CREATE INDEX IX_assignments_customer ON dbo.campaign_assignments(customer_id);
CREATE INDEX IX_assignments_treatment ON dbo.campaign_assignments(treatment);
CREATE INDEX IX_outcomes_customer ON dbo.outcomes(customer_id);
GO

PRINT 'Schema created successfully.';
GO