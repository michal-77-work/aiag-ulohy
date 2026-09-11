# Úloha C2

Navrhni a vytvoř agenta v no-code platformě, který pracuje s databází, používá nástroje
a odpovídá na dotazy přes LLM. Platforma: **LangFlow** (N8N vynechané).

## Návrh: databáza za vlastným, ručne napísaným MCP serverom (HTTP)

Databáza je agentovi sprístupnená cez **malý vlastný MCP server** napísaný v presne tom
istom štýle ako kurzový príklad `2_MCP/v1/3_STREAMABLE_HTTP/1_simplest_http/my_server` —
jeden čitateľný `server.py` (~140 riadkov). Server beží ako trvalý **Streamable HTTP**
endpoint, LangFlow sa naň pripája len URL adresou (`MCP Tools` nód), presne ako v kurze
`4_LangFlow/03-Agents/3-ai-agents/AI Agent - MCP.json` — len namiesto webu ide o databázu.

Predtým to riešil reťazec `mcp-proxy` + hotový `mcp-server-postgresql` (čierna skrinka).
Teraz je celá "databáza ako nástroj" logika v jednom súbore, ktorý vidíme a ovládame —
viď [`mcp_server/`](./mcp_server/).

Doména je zámerne iná než ecommerce, ktorý už použil prednášajúci: malá **IT helpdesk**
databáza s ticketmi (`tickets`).

## Architektúra

```
Docker: uloha-helpdesk-db (Postgres, :5432)
   rola "helpdesk_ro" — iba SELECT
              ▲
              │ SQL (localhost:5432)
              │
Host:  mcp_server/server.py  (uv run -m server, :8010, Streamable HTTP /mcp/)
   jeden nástroj: run_sql_query(query) — read-only SELECT nad tabuľkou tickets
              ▲
              │ Streamable HTTP (host.docker.internal:8010/mcp/)
              │
Docker: my_langflow (langflow-course:latest, :7860)
   Chat Input ──▶ Agent ──▶ Chat Output
                    ▲
                    │ tools
             MCP Tools  →  { "url": "http://host.docker.internal:8010/mcp/" }
             + built-in Calculator tool
             + built-in Current Date tool
```

| Uzol / komponent | Rola |
| --- | --- |
| **uloha-helpdesk-db** | Postgres s tabuľkou `tickets`, connection len cez read-only rolu `helpdesk_ro` |
| **mcp_server/server.py** | vlastný MCP server (Streamable HTTP, port 8010), vystavuje nástroj `run_sql_query` |
| **Chat Input / Chat Output** | vstup a výstup konverzácie |
| **Agent** (OpenAI `gpt-5-nano`) | rozhoduje, ktorý nástroj zavolať, a sformuluje finálnu odpoveď |
| **MCP Tools** → `db_access` | pripája sa **URL adresou** (`http://host.docker.internal:8010/mcp/`) na vlastný server |
| **Calculator** (built-in v Agente) | bezpečná aritmetika (počty, priemery, doba vyriešenia) |
| **Current Date** (built-in v Agente) | rieši relatívne dotazy typu "za posledný týždeň" |

### Prečo vlastný server namiesto mcp-proxy

`mcp-proxy` + `mcp-server-postgresql` bol funkčný, ale nepriehľadný a mal svoje úskalia
(napr. po chybe nechal poškodenú transakciu v poole). Vlastný `server.py` je čitateľný,
robí presne to, čo chceme, a každé volanie otvára čerstvé pripojenie — takže je
štrukturálne odolný voči tej chybe. Detaily v [`mcp_server/README.md`](./mcp_server/README.md).

### Read-only na dvoch úrovniach

1. `server.py` prepustí len `SELECT`/`WITH` dotazy.
2. Pripája sa cez Postgres rolu `helpdesk_ro` s grantom iba na `SELECT`.

Overené: pokus o `DELETE` cez nástroj zlyhá už na prvej vrstve, a aj keby prešiel, DB ho
odmietne.

## Dáta: `tickets` tabuľka

120 vygenerovaných helpdesk ticketov (`db/init.sql`, deterministický seed) so stĺpcami:
`id, subject, customer, category, priority, status, assigned_to, created_at, resolved_at`.

## Ako to spustiť

Docker príkazy sú zámerne na **jeden riadok** — fungujú bez úprav v `cmd.exe`, PowerShell
aj bash (`\` z bash a `` ` `` z PowerShell inak v cmd.exe nefungujú a naopak).

### 1. Postgres s dátami + read-only rola

```
docker run -d --name uloha-helpdesk-db -e POSTGRES_USER=helpdesk -e POSTGRES_PASSWORD=Heslo_1234 -e POSTGRES_DB=helpdesk -p 5432:5432 -v "C:\_WORKSPACES\aiag-ulohy\uloha-c2\db\init.sql:/docker-entrypoint-initdb.d/init.sql:ro" postgres:16-alpine
```

```
docker exec uloha-helpdesk-db psql -U helpdesk -d helpdesk -c "CREATE ROLE helpdesk_ro LOGIN PASSWORD 'Heslo_1234'; GRANT CONNECT ON DATABASE helpdesk TO helpdesk_ro; GRANT USAGE ON SCHEMA public TO helpdesk_ro; GRANT SELECT ON ALL TABLES IN SCHEMA public TO helpdesk_ro;"
```

(uprav cestu k `init.sql` v prvom príkaze, ak máš repozitár inde)

### 2. Vlastný MCP server (na hoste, nie v Dockeri)

```
cd uloha-c2/mcp_server
uv run -m server
```

Počúva na `http://0.0.0.0:8010`, MCP endpoint `/mcp/`. Nechaj ho bežať v samostatnom
termináli. (Databázu berie cez env premenné s defaultmi na `uloha-helpdesk-db` — netreba
nič nastavovať.)

### 3. LangFlow

Obraz `langflow-course:latest` (LangFlow + MSSQL ODBC driver, s opravou pre RHEL základ
obrazu) sa stavia z [`langflow/Dockerfile`](./langflow/Dockerfile) — raz, z koreňa
repozitára:

```
docker build -t langflow-course:latest uloha-c2/langflow
```

Potom LangFlow spusti:

```
docker run -d --name my_langflow -p 7860:7860 -e OPENAI_API_KEY=sk-... -e LANGFLOW_AUTO_LOGIN=true -e LANGFLOW_SKIP_AUTH_AUTO_LOGIN=true -e LANGFLOW_ALLOW_CUSTOM_COMPONENTS=true -e LANGFLOW_SSRF_ALLOWED_HOSTS=host.docker.internal,localhost,127.0.0.1 -e LANGFLOW_MCP_SERVER_ALLOWED_PACKAGES=mcp-proxy,lfx,mcp-server-fetch -e LANGFLOW_CONFIG_DIR=/app/langflow -v my_langflow_data:/app/langflow langflow-course:latest
```

(nahraď `sk-...` svojím skutočným kľúčom priamo v termináli — nikdy ho nezapisuj do súboru
v repozitári)

`LANGFLOW_MCP_SERVER_ALLOWED_PACKAGES` netreba meniť — LangFlow už nič nespúšťa cez `uvx`,
len volá našu HTTP URL.

Importuj `Helpdesk Tickets DB Agent (uloha-c2).json` cez UI a v Playgrounde (`http://localhost:7860`)
skús napr.:

- *"Koľko ticketov má status Open?"*
- *"Aký je priemerný čas vyriešenia ticketu s prioritou Critical?"* (SQL + Calculator)
- *"Koľko ticketov bolo vytvorených za posledný týždeň?"* (SQL + Current Date)

## Overenie počas prípravy

- Vlastný server naštartoval (`uv run -m server`) a MCP handshake cez
  `mcp.client.streamable_http.streamablehttp_client` vrátil nástroj `run_sql_query`;
  `SELECT status, COUNT(*) ...` vrátil správne dáta (Resolved 47 / Closed 30 /
  In Progress 25 / Open 18).
- Dostupnosť z Dockeru overená cez `host.docker.internal:8010/mcp/` (z kontajnera
  `langflow-course:latest`).
- Pokus o `DELETE` cez nástroj zamietnutý (`Only read-only SELECT/WITH queries are allowed`).
- **Celý flow reálne spustený cez LangFlow** (`POST /api/v1/run/`): na otázku
  *"How many tickets have status Open?"* agent zavolal `run_sql_query`, dostal dáta z DB a
  odpovedal *"18 tickets have status Open"* — správne.

> Pozn.: MCP URL **musí** končiť lomítkom (`/mcp/`). Bez neho vráti Starlette 307 redirect,
> ktorý LangFlow MCP klient nenasleduje a spadne na HTTP 307.
