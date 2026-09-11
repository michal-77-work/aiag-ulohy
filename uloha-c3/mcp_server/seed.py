"""Build vendors.db - the vendor / contract / incident database.

    uv run seed.py

Fictional vendors for a mid-size company. The data is generated with a fixed
seed, and it has ONE PLANTED SITUATION that a real procurement analyst would be
asked to untangle:

- Several contracts renew in Q4 2026 (Oct-Dec).
- ONE of them (Northwind Cloud Storage) is business-critical, auto-renews, is
  expensive, AND has a cluster of recent SEV1 outages plus an SLA breach. The
  correct recommendation is NOT to let it auto-renew - renegotiate the SLA or
  plan a replacement.
- Another Q4 renewal (Cedar Payroll) is clean -> renew.
- A third (Atlas Analytics) has no incidents, but its renewal_quote is 38%
  above the current annual_value -> review pricing.

The point, as in the course's data-analyst lesson: over uniform random data an
agent can only be asked questions with uninteresting answers. Here the internal
risk must be DETECTED (a cluster of incidents), not just listed, and the
external risk comes from the web.

"Today" for this dataset is around 2026-09-10, so Q4 2026 renewals are the ones
coming up.
"""

import random
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "vendors.db"

RNG = random.Random(20260910)

SCHEMA = """
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS contracts;
DROP TABLE IF EXISTS vendors;

CREATE TABLE vendors (
    vendor_id    INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    country      TEXT NOT NULL,
    criticality  TEXT NOT NULL   -- low | medium | high | critical
);

CREATE TABLE contracts (
    contract_id   INTEGER PRIMARY KEY,
    vendor_id     INTEGER NOT NULL REFERENCES vendors(vendor_id),
    service       TEXT NOT NULL,
    annual_value  REAL NOT NULL,
    renewal_quote REAL NOT NULL,   -- annual price the vendor quoted for the next term
    start_date    TEXT NOT NULL,   -- ISO date
    renewal_date  TEXT NOT NULL,   -- ISO date
    auto_renew    INTEGER NOT NULL,-- 0 | 1
    status        TEXT NOT NULL    -- active | expired
);

CREATE TABLE incidents (
    incident_id  INTEGER PRIMARY KEY,
    vendor_id    INTEGER NOT NULL REFERENCES vendors(vendor_id),
    date         TEXT NOT NULL,    -- ISO date
    type         TEXT NOT NULL,    -- outage | sla_breach | security | data_quality
    severity     TEXT NOT NULL,    -- SEV1 | SEV2 | SEV3
    description  TEXT NOT NULL
);
"""

# (vendor_id, name, category, country, criticality)
VENDORS = [
    (1, "Northwind Cloud Storage", "Cloud storage", "USA", "critical"),
    (2, "Cedar Payroll", "Payroll & HR", "Germany", "critical"),
    (3, "Atlas Analytics", "BI & analytics", "UK", "medium"),
    (4, "Beacon Email Security", "Email security", "USA", "high"),
    (5, "Meridian Print Services", "Office / print", "Slovakia", "low"),
    (6, "Orchard CRM", "CRM", "Ireland", "high"),
    (7, "Silverline Backups", "Backup & DR", "USA", "high"),
    (8, "Tundra Facilities", "Facilities", "Slovakia", "low"),
]

# (contract_id, vendor_id, service, annual_value, renewal_quote, start_date, renewal_date, auto_renew, status)
# Q4 2026 = 2026-10-01 .. 2026-12-31. Most quotes are a routine +3%.
CONTRACTS = [
    # The problem child: critical, auto-renews in Q4, expensive.
    (101, 1, "Primary object storage + CDN", 240000.0, 247200.0, "2023-11-15", "2026-11-15", 1, "active"),
    # Clean critical renewal in Q4.
    (102, 2, "Payroll processing (EU)", 96000.0, 98880.0, "2024-12-01", "2026-12-01", 1, "active"),
    # Steep price increase at renewal (+38% quote), no incidents.
    (103, 3, "Analytics platform", 72000.0, 99360.0, "2024-10-20", "2026-10-20", 0, "active"),
    # High criticality but renews next year - noise for the Q4 filter.
    (104, 4, "Inbound email filtering", 54000.0, 55620.0, "2025-03-01", "2027-03-01", 1, "active"),
    (105, 6, "CRM seats + support", 120000.0, 123600.0, "2024-06-15", "2027-06-15", 1, "active"),
    # Another Q4 renewal, high criticality, one minor incident only.
    (106, 7, "Offsite backup + DR", 84000.0, 86520.0, "2024-10-05", "2026-10-05", 1, "active"),
    # Low-criticality Q4 renewals - noise.
    (107, 5, "Managed print fleet", 18000.0, 18000.0, "2025-11-30", "2026-11-30", 1, "active"),
    (108, 8, "Facilities management", 26000.0, 26780.0, "2024-12-20", "2026-12-20", 0, "active"),
]

# (vendor_id, date, type, severity, description)
# Northwind (1): the planted cluster - 3x SEV1 outage + 1 SLA breach, all recent.
INCIDENTS = [
    (1, "2026-07-28", "outage", "SEV1", "Region us-east unavailable 3h20m, checkout blocked"),
    (1, "2026-08-14", "outage", "SEV1", "Global read latency spike, 5xx errors for 1h50m"),
    (1, "2026-09-02", "outage", "SEV1", "Object store write failures 2h, data ingestion stalled"),
    (1, "2026-09-05", "sla_breach", "SEV2", "Monthly uptime 99.1% vs 99.9% SLA - credits owed"),
    # Silverline (7): a single minor blip - should NOT tip it into 'risky'.
    (7, "2026-06-10", "data_quality", "SEV3", "One nightly backup job retried, completed late"),
    # Beacon (4): older, and it renews next year anyway.
    (4, "2026-02-19", "security", "SEV2", "False-positive quarantine of finance mailbox 40min"),
]


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT INTO vendors VALUES (?, ?, ?, ?, ?)", VENDORS
        )
        con.executemany(
            "INSERT INTO contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", CONTRACTS
        )
        con.executemany(
            "INSERT INTO incidents VALUES (NULL, ?, ?, ?, ?, ?)", INCIDENTS
        )
        con.commit()

        v = con.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
        c = con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        i = con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        q4 = con.execute(
            "SELECT COUNT(*) FROM contracts "
            "WHERE renewal_date BETWEEN '2026-10-01' AND '2026-12-31'"
        ).fetchone()[0]
    finally:
        con.close()

    print(f"Wrote {DB_PATH.name}: {v} vendors, {c} contracts ({q4} renewing in Q4), {i} incidents")


if __name__ == "__main__":
    main()
