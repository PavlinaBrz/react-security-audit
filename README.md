# 🛡️ React Security Audit Pipeline

Multi-agent orchestration pro automatizovaný bezpečnostní audit React projektů.

**Projekt pro kurz Vibe Coding / Agentic Engineering** (robot_dreams, lekce 5)

## Co to dělá

Zadáte cestu k React projektu a systém ho automaticky prověří přes **tým specializovaných AI agentů**. Na konci dostanete strukturovaný Markdown report se všemi nálezy a doporučeními.

```
uv run python main.py /cesta/k/react-projektu
```

## Demonstrované orchestrace

| Pattern | Typ | Fáze | Popis |
|---------|-----|------|-------|
| **Parallel** | Workflow | Fáze 1 | 3 agenti skenují projekt současně (fan-out / fan-in) |
| **Supervisor** | Multi-agent | Fáze 2 | Supervisor kontroluje kvalitu reportů, rozhoduje přes structured output |
| **Loop** | Workflow | Fáze 2 | Pokud je report neúplný, agent dostane feedback a zkusí znovu (max 2×) |
| **Sequential** | Workflow | Fáze 3 | Report Generator zkompiluje finální report ze všech nálezů |

## Architektura

```
Uživatel zadá cestu k React projektu
              │
    ┌─────────▼──────────┐
    │  PARALLEL WORKFLOW  │  Fáze 1: Fan-out — 3 agenti současně
    │  (anyio task group) │
    └──┬──────┬──────┬────┘
       │      │      │
  ┌────▼──┐ ┌─▼───┐ ┌▼────────┐
  │🔒 Sec.│ │📋 QA│ │📦 Deps  │   Každý agent má vlastní ClaudeSDKClient
  │Scanner│ │     │ │ Auditor │   + vlastní tools (Read, Glob, Grep)
  └───┬───┘ └──┬──┘ └──┬──────┘
      │        │       │
    ┌─▼────────▼───────▼─┐
    │  SUPERVISOR REVIEW  │  Fáze 2: Kontrola kvality
    │  (structured output)│
    └─────────┬───────────┘
              │
         all_complete?
        /           \
      YES            NO → LOOP: pošli agenta zpět s feedbackem
       │                        (max 2 iterace)
       │
    ┌──▼──────────────────┐
    │  REPORT GENERATOR   │  Fáze 3: Sequential — kompilace reportu
    │  (Markdown output)  │
    └─────────────────────┘
              │
    📄 audit_report_YYYYMMDD.md
```

## Tým agentů

### 🔒 Security Scanner
Hledá bezpečnostní zranitelnosti:
- XSS (dangerouslySetInnerHTML, unescaped input)
- Hardcoded secrets (API klíče, tokeny v kódu)
- Nezabezpečené API volání (HTTP, chybějící auth)
- Nebezpečné `eval()` / `Function()`
- Insecure storage (citlivá data v localStorage)

### 📋 Code Quality Reviewer
Kontroluje kvalitu kódu:
- Chybějící error boundaries
- Chybějící error handling v async operacích
- Memory leaky (useEffect cleanup)
- Performance anti-patterny
- Accessibility issues
- Console.log v produkci

### 📦 Dependency Auditor
Kontroluje závislosti:
- Známé zranitelné balíčky (CVE)
- Zastaralé verze kritických balíčků
- Podezřelé nebo neznámé balíčky
- Chybějící security balíčky (helmet, cors)
- Licenční problémy

### 🎯 Audit Supervisor
Koordinuje celý audit:
- Kontroluje kvalitu reportů od všech agentů
- Rozhoduje přes structured output (JSON schema)
- Pokud report nestačí, pošle agenta zpět (Loop)
- Sám nikdy nekontroluje kód — jen řídí

### 📝 Report Generator
Kompiluje finální report:
- Shrnutí (executive summary)
- Bezpečnostní nálezy
- Kvalita kódu
- Závislosti
- Prioritizovaná doporučení

## Klíčové koncepty z kurzu

### Tool Calling (lekce 1)
Agenti používají vestavěné Claude Code tools: `Read` (čtení souborů), `Glob` (hledání souborů), `Grep` (hledání v obsahu). Model si sám rozhodne, které soubory potřebuje přečíst.

### ReAct smyčka (lekce 1)
Každý agent běží v ReAct smyčce — čte soubor → analyzuje → potřebuje další soubor → přečte → … → vrátí report. Smyčku řídí Claude Agent SDK automaticky.

### Structured Output (lekce 3)
Supervisor vrací rozhodnutí v pevném JSON formátu (schema):
```json
{
  "all_complete": false,
  "incomplete_agent": "🔒 Security Scanner",
  "feedback": "Report je příliš vágní, chybí konkrétní soubory a čísla řádků",
  "summary": "Security Scanner potřebuje doplnit detaily"
}
```

### Parallel Workflow (lekce 5)
Tři agenti běží současně přes `anyio.create_task_group()` — fan-out / fan-in pattern. Nezávisí na sobě, takže paralelizace šetří čas.

### Supervisor Pattern (lekce 5)
Supervisor je „manažer" — sám nekontroluje kód, jen řídí tým. Rozhoduje přes structured output: je to dost dobré, nebo potřebuju víc?

### Loop Workflow (lekce 5)
Pokud Supervisor vyhodnotí report jako nedostatečný, agent dostane zpětnou vazbu a zkusí to znovu. Iterativní vylepšování s max 2 opakováními.

## Instalace a spuštění

### Požadavky
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Claude Code nainstalovaný (`curl -fsSL https://claude.ai/install.sh | bash`)
- Anthropic Pro/Max subskripce (Claude Code vyžaduje)

### Setup

```bash
# Naklonuj repozitář
git clone https://github.com/PavlinaBrz/react-security-audit.git
cd react-security-audit

# Vytvoř prostředí a nainstaluj závislosti
uv venv
source .venv/bin/activate
uv sync
```

### Spuštění

```bash
# Audit React projektu v zadané složce
uv run python main.py /cesta/k/react-projektu

# Audit projektu v aktuální složce
uv run python main.py
```

### Ukázkový výstup

```
======================================================================
🛡️  REACT SECURITY AUDIT PIPELINE
======================================================================

   Projekt: /home/user/my-react-app
   Čas:     2026-04-26 14:30

   Orchestrace:
     • Parallel workflow  — 3 agenti skenují současně
     • Supervisor pattern — kontrola kvality výsledků
     • Loop workflow      — iterativní vylepšení (max 2×)
     • Sequential         — kompilace finálního reportu

======================================================================
📡 FÁZE 1: PARALELNÍ SKENOVÁNÍ (Parallel Workflow)
======================================================================
   ▶ 🔒 Security Scanner — spuštěn
   ▶ 📋 Code Quality — spuštěn
   ▶ 📦 Dependency Auditor — spuštěn
    🔧 🔒 Security Scanner → Glob
    🔧 🔒 Security Scanner → Read
    🔧 📦 Dependency Auditor → Read
    ...
   ✅ 📦 Dependency Auditor — dokončen (1847 znaků)
   ✅ 📋 Code Quality — dokončen (2103 znaků)
   ✅ 🔒 Security Scanner — dokončen (3219 znaků)

======================================================================
🎯 FÁZE 2: SUPERVISOR REVIEW + LOOP (Supervisor + Loop)
======================================================================
   📋 Supervisor review — iterace 1/2
    📝 Security Scanner report je dostatečný, ale Code Quality...
    🔄 Loop: posílám '📋 Code Quality' zpět s feedbackem
   ✅ 📋 Code Quality — vylepšený report (2891 znaků)

   📋 Supervisor review — iterace 2/2
    ✅ Supervisor: Všechny reporty jsou kompletní.

======================================================================
📝 FÁZE 3: GENEROVÁNÍ REPORTU (Sequential)
======================================================================

======================================================================
✅ AUDIT DOKONČEN
======================================================================

   📄 Report uložen: /home/user/my-react-app/audit_report_20260426_143012.md
```

## Struktura projektu

```
react-security-audit/
├── main.py            # Celý pipeline — Parallel + Supervisor + Loop + Sequential
├── pyproject.toml     # Závislosti (claude-agent-sdk, anyio)
├── README.md          # Tento soubor
└── .gitignore
```

## Proč jeden soubor?

Projekt je záměrně v jednom souboru `main.py` — stejně jako lektorovy ukázky v kurzu. Každá orchestrace je jasně oddělená komentáři a sekcemi:

1. `run_parallel_scan()` — Parallel workflow
2. `run_supervisor_review()` — Supervisor + Loop
3. `generate_report()` — Sequential (report)
4. `run_audit()` — hlavní pipeline spojující vše

## Technické poznámky

- Používá **Claude Agent SDK** (`claude-agent-sdk`) — Python SDK pro programatické ovládání Claude Code
- Každý agent běží ve vlastní izolované `ClaudeSDKClient` session (vlastní kontext)
- Agenti čtou soubory projektu přes vestavěné tools (Read, Glob, Grep)
- Supervisor rozhoduje přes **structured output** (JSON schema)
- Paralelní běh přes `anyio.create_task_group()` (fan-out / fan-in)
- Report se uloží jako Markdown soubor do auditovaného projektu

## Autor

Projekt pro kurz Vibe Coding / Agentic Engineering (robot_dreams, 2026).
Lektor: Lukáš Kellerstein.