# Úloha C1

Napíš Python skript, který zavolá LLM API, použije nástroj (tool / function calling) a vrátí odpověď zpět LLM.

## Zadanie

1. Zavolaj OpenAI Chat Completions API so správou od používateľa, ktorá sa dá zodpovedať len pomocou nástroja.
2. Definuj nástroj `get_weather(city)`, ktorý zavolá verejné [Open-Meteo](https://open-meteo.com/) API
   (najprv geokódovanie mesta na súradnice, potom aktuálne počasie) — nevyžaduje žiadny API kľúč.
3. Ak model vráti `tool_calls`, spusti príslušnú Python funkciu, výsledok pridaj do histórie správ ako
   správu s rolou `tool` a znovu zavolaj API, aby model sformuloval finálnu odpoveď v prirodzenom jazyku.

Toto zámerne nepoužíva rovnaký nástroj (`get_stock_price` / `get_dividend_date` cez `yfinance`) ako ostatné
príklady v `1_llm_api/*/4_tools`.

## Run

### Priamo

```bash
uv run main.py
```

### Cez virtuálne prostredie

Vytvor virtuálne prostredie

```bash
uv venv
```

Aktivuj virtuálne prostredie

```bash
source .venv/bin/activate
```

Nainštaluj balíčky

```bash
uv sync
```

Skopíruj `.env.example` na `.env` a doplň svoj `OPENAI_API_KEY`

Spusti skript

```bash
python main.py
```
