# Helpdesk DB — vlastný MCP server (Streamable HTTP)

Malý, ručne napísaný MCP server v presne tom istom štýle ako
`2_MCP/v1/3_STREAMABLE_HTTP/1_simplest_http/my_server` — jeden čitateľný `server.py`.
Nahrádza komplikovaný reťazec `mcp-proxy` + `mcp-server-postgresql` z predošlej verzie.

Vystavuje jeden nástroj:

- **`run_sql_query(query)`** — spustí read-only `SELECT`/`WITH` dotaz nad Postgres
  databázou `helpdesk` a vráti riadky ako JSON. Schéma tabuľky `tickets` je priamo v
  popise nástroja, takže LLM vie, aké stĺpce má k dispozícii.

## Bezpečnosť — dve vrstvy read-only

1. `server.py` prepustí len dotazy začínajúce `SELECT`/`WITH` (blokne `INSERT`/`DELETE`/…).
2. Pripája sa cez Postgres rolu `helpdesk_ro`, ktorá má grantnuté iba `SELECT` — takže aj
   keby prvá vrstva zlyhala, databáza zápis odmietne.

Každé volanie otvára čerstvé pripojenie (žiadny pool), čím sa štrukturálne vyhýbame chybe
"current transaction is aborted", na ktorú sme narazili pri `mcp-server-postgresql`.

## Spustenie

Beží priamo na hoste (nie v Dockeri), rovnako ako kurzové príklady:

```
uv run -m server
```

Server počúva na `http://0.0.0.0:8010`, MCP endpoint je na **`/mcp/`** (koncové lomítko je
dôležité — `/mcp` bez neho vráti 307 redirect, ktorý LangFlow klient nenasleduje).

Databázu konfiguruješ cez env premenné (defaulty sedia na `uloha-helpdesk-db`):
`PGHOST` (localhost), `PGPORT` (5432), `PGUSER` (helpdesk_ro), `PGPASSWORD` (Heslo_1234),
`PGDATABASE` (helpdesk), `PORT` (8010).

LangFlow (v Dockeri) sa naň pripája na `http://host.docker.internal:8010/mcp/`.
