# Úloha C3 — Vendor Risk & Renewal agent (Plan-Execute)

Navrhni a vytvoř agenta pomocí frameworku, který pracuje s nástroji a odpovídá na dotazy
přes LLM. Zvaž použití MCP místo framework-specific toolů.

- **Framework:** LangChain (LangChain 1.x), bez LangGraph. Každá rola Plan-Execute vzoru má
  vlastný súbor: `planner.py` a `replanner.py` sú po jednom LLM volaní so structured output,
  `executor.py` je malá tool-calling slučka (`bind_tools`) a celá plan→execute→replan
  slučka je jedna funkcia `run_agent()` v `agent.py`.
- **Agent typ:** Plan-Execute.
- **Nástroje:** databáza **cez MCP** (`run_sql_query`) + webový vyhľadávač **Tavily** +
  `get_current_date` (dnešný dátum a kvartál).
- **LLM:** OpenAI `gpt-5.6-luna` (dá sa zmeniť cez `OPENAI_MODEL` v `agent/.env`). Volá sa
  cez OpenAI **Responses API** — gpt-5.6 modely v Chat Completions API nepodporujú nástroje
  spolu s reasoningom.

## Use case

Vendor risk / obnova zmlúv. Otázka typu *„Ktorí Q4 dodávatelia sú rizikoví a prečo?
Odporuč akciu."* Agent skombinuje **interné dáta** (kto sa obnovuje, naše incidenty
s dodávateľom) s **externým webom** (najnovšie správy) a vydá odporúčanie
*renew / renegotiate / replace / review* so zdrojmi.

## Prečo Plan-Execute (a nie obyčajný ReAct)

Úloha si pýta dekompozíciu dopredu a adaptáciu:
1. z DB nájdi, ktoré kontrakty sa obnovujú v Q4,
2. z DB zisti interné rizikové signály (incidenty, hodnota, kritickosť),
3. **až potom** choď na web skúmať *len* tých, čo vyzerajú rizikovo/kriticky (šetrí kroky),
4. zostav odporúčanie.

Krok 3 závisí od výsledku krokov 1–2 — to je práca **replannera**, ktorý po každom kroku
buď doplní/upraví zvyšok plánu, alebo vyhlási úlohu za hotovú a zloží finálnu odpoveď.

## Architektúra

![Plan-Execute graf](agent/graph.png)

Vygeneruješ ho `uv run visualizer.py` (v `agent/`, renderuje cez mermaid.ink).

```
otázka
  │
  ▼
PLANNER    (planner.py)    → zoznam krokov
  │
  ▼
┌─ slučka v agent.py (max 8 cyklov) ─────────────────────────────
│  EXECUTOR  (executor.py)   → vykoná JEDEN krok tool-calling slučkou:
│                              model → nástroj → výsledok → model → … → výsledok kroku
│      ├─ run_sql_query / describe_schema   MCP server :8020 → vendors.db (read-only)
│      ├─ get_current_date
│      └─ web_search                        Tavily
│  REPLANNER (replanner.py)  → COMPLETE: finálna odpoveď
│                              CONTINUE: ďalší krok (plán rovnaký alebo zmenený)
└─ späť na EXECUTOR ─────────────────────────────────────────────
```

- **Databáza je MCP nástroj, nie framework-specific tool.** `mcp_server/server.py` je malý
  Streamable-HTTP MCP server (rovnaký vzor ako `uloha-c2/mcp_server`) nad `vendors.db`,
  vystavuje `run_sql_query` (read-only). Agent ho konzumuje cez `langchain-mcp-adapters`,
  takže ho „vidí" ako bežný LangChain tool.
- **Web je LangChain tool** — Tavily (`langchain-tavily`), obalený v `agent/tools.py`.
- **Dnešný dátum je tiež nástroj** — `get_current_date` (LangChain `@tool` v
  `agent/tools.py`) vráti dnešný dátum a aktuálny kvartál. Model nemá hodiny a dátum
  natvrdo v prompte by časom zastaral, takže executor si ho vyžiada vždy, keď rieši niečo
  relatívne k dnešku („Q4" bez roka, „za posledných 30 dní", „najbližšie obnovy").

## Dáta a „ťažký problém"

`mcp_server/seed.py` (fixný seed) vytvorí `vendors`, `contracts`, `incidents`. Nasadený twist:
**Northwind Cloud Storage** — kritický, auto-renew, $240k, obnova 2026-11-15 — má zhluk
3× SEV1 výpadkov + SLA breach za posledné ~6 týždňov. Správne odporúčanie je *neísť do
auto-renew, renegotiovať SLA / plánovať náhradu*. **Cedar Payroll** je čistý → renew.
**Atlas Analytics** nemá incidenty, ale jeho `renewal_quote` (cena ponúknutá na ďalšie
obdobie) je o 38 % vyššia než `annual_value` → review pricing.

Agent musí interné riziko **detekovať SQL agregáciou** (nie len vypísať), rozhodnúť sa,
koho ísť skúmať na web, a skombinovať interné + externé do obhájiteľného odporúčania.
Databáza je **read-only na dvoch úrovniach** (keyword screen v `db.py` + SQLite `mode=ro`),
takže deštruktívna požiadavka („zruš zmluvu") sa odmietne a agent len poradí.

Dataset je navrhnutý k septembru 2026. Otázky relatívne k dnešku („Q4" bez roka, „za
posledných 30 dní") agent rieši cez `get_current_date` podľa **reálneho** dátumu — pri
neskoršom spustení preto uvádzaj rok explicitne (napr. „Q4 2026").

## Súbory

```
uloha-c3/
  mcp_server/
    server.py    # Streamable HTTP MCP server, tool run_sql_query / describe_schema
    db.py        # schema + SQL safety layer + read-only connection
    seed.py      # vytvorí vendors.db (planted twist)
  agent/
    main.py        # spustenie: načíta nástroje a položí otázky
    agent.py       # slučka plan → execute → replan (jedna funkcia run_agent)
    planner.py     # PLAN: otázka → zoznam krokov
    executor.py    # EXECUTE: jeden krok cez tool-calling slučku (vidno každé volanie nástroja)
    replanner.py   # REPLAN: COMPLETE (odpoveď) alebo CONTINUE (zvyšok plánu)
    tools.py       # Tavily web_search + get_current_date @tool
    mcp_client.py  # načíta DB nástroje z MCP servera (langchain-mcp-adapters)
    model.py       # get_model → OpenAI gpt-5.6-luna
    visualizer.py  # vykreslí graph.png
  .env.example
```

## Ako to spustiť

Potrebuješ `OPENAI_API_KEY` a `TAVILY_API_KEY` (Tavily má free tier).

```
cp .env.example agent/.env      # a doplň oba kľúče
```

**1. Postav databázu** (raz, a znova po každej zmene `seed.py`):
```
cd uloha-c3/mcp_server
uv run seed.py
```

**2. Spusti MCP server** (nechaj bežať v samostatnom termináli):
```
cd uloha-c3/mcp_server
uv run -m server
```
Počúva na `http://localhost:8020/mcp/`.

**3. Spusti agenta** (iný terminál):
```
cd uloha-c3/agent
uv run main.py                       # scripted otázky
uv run main.py "tvoja otázka"
```

## Scripted otázky (`main.py`)

| # | Otázka | Čo cvičí |
|---|--------|----------|
| 1 | Ktoré kontrakty sa obnovujú v Q4 a akú majú hodnotu? | čistý DB krok, žiadny web |
| 2 | Ktorí Q4 dodávatelia sú rizikoví a prečo? Odporuč akciu. | plný Plan-Execute → nájde nasadený incident cluster, doskúma na webe |
| 3 | Priprav obnovovací briefing pre kritických dodávateľov. | loop cez záznamy + web |
| 4 | Zruš zmluvu s Northwind… | nie je to dotaz — ukáže read-only / „len poradím" hranicu |

## Ako čítať výstup (log)

| Značka | Čo znamená |
|---|---|
| `📋 PLAN` | planner vytvoril plán (zoznam krokov) |
| `🚀 EXECUTE (cycle N)` | executor robí jeden krok; `▶ step` je krok, ktorý práve rieši |
| `🤖 model call i/8` | jedno volanie LLM v rámci kroku — každé kolo s nástrojom je nové volanie |
| `🔧 nástroj(argumenty)` | model si vyžiadal nástroj; vidno presné argumenty (napr. SQL, ktoré napísal) |
| `↳` | výsledok nástroja, ktorý sa vracia modelu |
| `💬 step result` | model už nástroj nechce — krok je hotový |
| `🔄 REPLAN` | replanner rozhodol `COMPLETE` / `CONTINUE` a za pomlčkou napísal prečo |
| `🔀 PLAN CHANGED` | replanner prepísal zvyšok plánu (počíta sa aj preformulovanie kroku) |
| `▶ plan unchanged` | pokračuje sa podľa doterajšieho plánu |
| `🏁` | koniec: počet cyklov a preplánovaní |

Skrátený skutočný výstup (otázka č. 2, `gpt-5.6-luna`, beh 2026-09-11; dlhé SQL a výsledky
skrátené `…`):

```
📋 PLAN
📝 plan (4 steps):
   1. Query the database for vendors with contracts renewing in Q4, including vendor name, …
   2. Query the database for recent internal risk signals for those Q4 vendors, …
   3. Identify which Q4 vendors warrant risk review … then search the web … for those vendors only.
   4. Produce a recommendation for each Q4 vendor, …

🚀 EXECUTE   (cycle 1)
   ▶ step: Query the database for vendors with contracts renewing in Q4, …
   🤖 model call 1/8
   🔧 get_current_date({})
      ↳ Today is 2026-09-11 (Friday). Current quarter: Q3 2026 (2026-07-01 to 2026-09-30).
   🤖 model call 2/8
   🔧 run_sql_query({'query': "SELECT v.name AS vendor_name, … WHERE c.renewal_date BETWEEN '2026-10-01' AND '2026-12-31' …"})
      ↳ {"row_count": 6, …}
   🤖 model call 3/8
   💬 step result: Q4 2026 contract renewals: …

🔄 REPLAN   (cycle 1)
   decision: CONTINUE — The Q4 contract list is complete, but recent incidents and renewal-price comparisons have not yet been queried, …
   🔀 PLAN CHANGED (replan #1) - remaining steps:
      1. Query the database for each Q4 vendor’s incidents from approximately the last 90 days and compare renewal quote with annual value.
      2. Classify each vendor using the incident and pricing rules: …
      …

🚀 EXECUTE   (cycle 2)
   ▶ step: Query the database for each Q4 vendor’s incidents from approximately the last 90 days and compare renewal quote with annual value.
   …
   🔧 run_sql_query({'query': "SELECT v.name AS vendor, … LEFT JOIN incidents i ON … AND i.date BETWEEN '2026-06-13' AND '2026-09-11' …"})
      ↳ {"row_count": 9, …}
   🤖 model call 3/8
   💬 step result: … **Atlas Analytics:** No incidents. … (**+$27,360, +38%**). **Northwind Cloud Storage:** Four incidents: …

🔄 REPLAN   (cycle 2)
   decision: CONTINUE — Incident and pricing data identify Northwind Cloud Storage for renegotiation/replacement and Atlas Analytics for pricing review, but required exact-company web searches have not been completed.
   🔀 PLAN CHANGED (replan #2) - remaining steps:
      1. Web-search Northwind Cloud Storage for recent exact-company breaches, outages, bankruptcies, or acquisitions, …
      2. Web-search Atlas Analytics for recent exact-company breaches, outages, bankruptcies, or acquisitions, …
      3. Produce one recommendation per Q4 vendor using the incident and pricing rules, …

🚀 EXECUTE   (cycle 3)
   ▶ step: Web-search Northwind Cloud Storage for recent exact-company breaches, outages, bankruptcies, or acquisitions, …
   🤖 model call 1/8
   🔧 web_search({'query': '"Northwind Cloud Storage" outage breach acquisition bankruptcy'})
      ↳ Product: Cloud Outage …
   🔧 web_search({'query': '"Northwind Cloud Storage"'})
      ↳ Northwind Self Storage | LinkedIn …
   🤖 model call 2/8
   💬 step result: No vendor-specific news found for the exact company **Northwind Cloud Storage**. Search results referred to unrelated entities, including Northwind Midstream and Northwind Self Storage; …

🔄 REPLAN   (cycle 3)
   decision: CONTINUE — Atlas Analytics exceeds the 10% pricing threshold and must be web-searched before recommending an action.
   ▶ plan unchanged - remaining steps:
      …

🚀 EXECUTE   (cycle 4)
   …
   🔧 web_search({'query': '"Atlas Analytics" breach OR outage OR bankruptcy OR acquisition 2026'})
      ↳ Downdetector - Check real-time service problems and ... …
   🔧 web_search({'query': '"Atlas Analytics" company news security incident service outage acquisition'})
      ↳ 10 Best Incident Response Softwares & Tools in 2026 …
   🤖 model call 3/8
   💬 step result: **Atlas Analytics:** No vendor-specific news found for the exact company … Search results were unrelated or non-news pages, …

🔄 REPLAN   (cycle 4)
   decision: COMPLETE — All Q4 vendors have incident and pricing data, and the two vendors requiring adverse action were web-searched.

🏁 COMPLETED · 4 cycle(s) · 2 replan(s)
```

Na čo sa pozrieť:
- **Preplánovanie v praxi:** po cykle 1 replanner doplnil do plánu klasifikáciu podľa pravidiel
  a po cykle 2 zúžil webový prieskum len na Northwind a Atlas Analytics — presne tá adaptácia,
  kvôli ktorej je tu Plan-Execute.
- **Web len tam, kde treba:** hľadá sa len pri dodávateľoch s odporúčanou zmenou, s presným
  názvom v úvodzovkách a najviac 2× na firmu.
- **Rozlíšenie firiem:** výsledky o *Northwind Self Storage* či *Atlas Systems* agent označil
  za nesúvisiace a nepoužil ich ako dôkaz.
- **Dôvody replannera** priamo citujú pravidlá („must be web-searched before recommending").

## Overenie počas prípravy

- `seed.py` vytvoril DB; kontrolný SQL potvrdil nasadený signál (Northwind: 3× SEV1,
  4 incidenty, kritický, auto-renew, $240k, Q4). Safety layer odmietol `DELETE`.
- MCP server naštartoval (Streamable HTTP `:8020/mcp/`, `initialize` → 200).
- **MCP prepojenie agenta overené end-to-end**: `langchain-mcp-adapters` sa pripojil,
  načítal tooly (`run_sql_query`, `describe_schema`) a reálne spustil SQL cez MCP.
- Po zjednodušení (samostatné `planner.py` / `executor.py` / `replanner.py`, vlastná
  tool-calling slučka namiesto `create_agent`) spustený celý beh otázky č. 2 — skrátený
  výstup je vyššie v sekcii „Ako čítať výstup".
- Plný LLM beh so skutočnými `OPENAI_API_KEY` a `TAVILY_API_KEY` spustený a funkčný.
- `get_current_date` vráti reálny dátum a správne hranice kvartálu (overené pre všetkých
  12 mesiacov). Pri behu 2026-09-11 na kroku *„Which vendors had incidents in the last 30
  days, and when do their contracts renew?"* executor najprv zavolal `get_current_date`,
  odvodil z neho `date BETWEEN '2026-08-12' AND '2026-09-11'` a správne odpovedal
  Northwind Cloud Storage (obnova 2026-11-15).

### Kvalita odpovede

S pôvodným `gpt-5-nano` odpovede porušovali pravidlá: Atlas Analytics (+38 %) dostal *renew*
namiesto *review pricing*, správy o iných firmách s podobným menom (F5 Silverline, Cedar
healthcare) bral ako dôkaz, jedného dodávateľa v odpovedi vynechal a pri faktickej otázke
robil zbytočnú rizikovú analýzu. Zmenilo sa:

- **Dáta:** pribudol stĺpec `renewal_quote` — +38 % bolo predtým len v texte popisu služby,
  takže sa to SQL-kom nedalo nájsť.
- **Prompty:** planner vie, aké dáta v DB sú; executor uvádza mená dodávateľov, za dôkaz
  berie len výsledok o presne tej istej firme a hľadá najviac 2× na firmu; replanner má
  pravidlá odporúčania, smie tvrdiť len to, čo niektorý krok vrátil, a rozlišuje
  „not searched" od „no vendor-specific news found".
- **Model:** `gpt-5.6-luna` cez Responses API.

Výsledok (otázka č. 2, 2026-09-11): Northwind → nepredĺžiť automaticky, renegotiate/replace;
Atlas Analytics → review pricing; Cedar Payroll, Silverline Backups, Meridian Print Services,
Tundra Facilities → renew. Všetkých 6 odporúčaní zodpovedá zámeru v dátach.

Ostatné scripted otázky (2026-09-11, `gpt-5.6-luna`):

- **č. 1** (zoznam Q4 kontraktov): 1 cyklus, jeden SQL dotaz, žiadne hľadanie na webe, len
  fakty — 6 kontraktov s ročnou hodnotou, bez odporúčaní.
- **č. 3** (briefing pre kritických dodávateľov): „business-critical" vyložil ako kritickosť
  high/critical (5 dodávateľov). Incidenty dotazoval skôr, než o nich niečo tvrdil; Northwind →
  renegotiate/replace (vyhľadaný na webe), ostatní → renew (SEV3 pri Silverline aj SEV2 pri
  Beacon sú mimo 90-dňového okna).
- **č. 4** (zruš zmluvu s Northwind): v databáze nič nezmenil, dotazoval incidenty aj web a
  odporučil nepredĺžiť automaticky a pripraviť náhradu s ohľadom na výpovedné lehoty v zmluve.

Model sa môže beh od behu správať mierne inak — toto sú výsledky jedného behu každej otázky.
