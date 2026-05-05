# 🛡️ React & TypeScript Comprehensive Audit

Kompletní audit React projektů přes tým 5 specializovaných AI agentů — **Swarm architektura**.

**Projekt pro kurz Vibe Coding**

## Co to dělá

Zadáte cestu k React projektu a systém ho automaticky prověří přes pět specializovaných agentů. Pokrývá bezpečnost, závislosti, kvalitu kódu, React patterns i TypeScript. Na konci dostanete strukturovaný Markdown report se všemi nálezy, seřazenými doporučeními a celkovým hodnocením rizika.

```bash
uv run python main.py /cesta/k/react-projektu
```

## Proč Swarm místo původního Supervisor + Loop?

Původní architektura měla jednoho Supervisora, který hodnotil tři agenty. Se třemi doménami (bezpečnost, kvalita, závislosti) to fungovalo. S pěti agenty a dvěma novými specializovanými doménami (React patterns, TypeScript) by Supervisor musel rozumět všemu — a feedback by byl povrchní.

Swarm jde jinou cestou: místo opakování vsází na **kvalitu jednoho průchodu**. Každý agent dostane přesný, hluboký system prompt pro svou doménu a projekt správně přiřazené soubory od Orchestrátora. Collaboration fáze pak zachytí průniky mezi React a TypeScript bez dalšího skenování kódu.

## Demonstrované orchestrace

| Pattern | Vzor | Fáze | Popis |
|---------|------|------|-------|
| **Sequential** | Workflow | Fáze 1 | Orchestrátor zmapuje projekt, structured output |
| **Parallel** | Workflow | Fáze 2 | 5 agentů skenuje současně (fan-out / fan-in) |
| **Collaboration** | Multi-agent | Fáze 3 | React ↔ TypeScript cross-review (vzájemný kontext) |
| **Sequential** | Workflow | Fáze 4 | Report Generator zkompiluje finální report |

## Architektura

```
Uživatel zadá cestu k React projektu
              │
    ┌─────────▼──────────────────────────┐
    │  ORCHESTRÁTOR (Fáze 1)             │  Structured output (JSON schema)
    │  Glob → inventář → strategie       │  Výstup: file_count, strategy, modules
    └─────────┬──────────────────────────┘
              │
         < 100 souborů?
        /              \
      ANO               NE
  volný přístup    přiřazení modulů
        \              /
    ┌────▼──────────────▼────────────────┐
    │  SWARM — 5 agentů paralelně       │  Fáze 2: Fan-out / fan-in
    │  (anyio.create_task_group)        │  anyio.Lock() pro sdílený slovník
    └──┬──────┬──────┬──────┬──────┬────┘
       │      │      │      │      │
  ┌────▼──┐ ┌─▼──┐ ┌─▼──┐ ┌▼───┐ ┌▼────┐
  │🔒 Sec.│ │📦  │ │📋  │ │⚛️  │ │🔷   │
  │Scanner│ │Dep.│ │QA  │ │React│ │TS   │
  └───┬───┘ └─┬──┘ └─┬──┘ └┬───┘ └┬────┘
      │       │      │     │      │
      └───────┘      │     └──────┘
          │          │         │
  bezpečnostní    kódová    ┌──▼──────────┐
    doména       kvalita    │ COLLABORATION│  Fáze 3: React ↔ TS cross-review
                            │ (parallel)  │  Průniky: hooks types, generika,
                            └──┬──────────┘  any v event handlerech
                               │
                    ┌──────────▼──────────┐
                    │  REPORT GENERATOR   │  Fáze 4: Sequential
                    │  (bez tools)        │  Vstupy oříznuty na 4000 znaků/agent
                    └──────────┬──────────┘
                               │
                   📄 audit_report_YYYYMMDD.md
```

## Tým agentů

### 🗺️ Orchestrátor
Není auditní agent — je to router a plánovač:
- Zmapuje projekt přes Glob (Structured output / JSON schema)
- Spočítá zdrojové soubory, detekuje TypeScript a package.json
- Pod 100 souborů: agenti prohledají projekt sami (`free` strategie)
- 100+ souborů: sestaví mapu modulů podle adresářové struktury (`modular` strategie) a přiřadí každému agentovi konkrétní seznam souborů — eliminuje riziko, že agent přečte jen prvních 20 souborů a zbytek ignoruje

### 🔒 Security Scanner
Hledá bezpečnostní zranitelnosti:
- XSS (dangerouslySetInnerHTML, unescaped user input v JSX)
- Hardcoded secrets (API klíče, tokeny, hesla přímo v kódu)
- Nezabezpečené API volání (HTTP, chybějící auth headers)
- Nebezpečné `eval()` / `Function()` konstruktor
- Prototype pollution
- Insecure storage (citlivá data v localStorage/sessionStorage)
- Chybějící CSRF ochrana ve formulářích a API mutacích
- Open redirects (nevalidované redirect targets)
- Unsafe `window.postMessage` bez origin validace
- Porušení Content Security Policy

### 📦 Dependency Auditor
Kontroluje závislosti a balíčky:
- Známé zranitelné balíčky (CVE pro React ekosystém)
- Kriticky zastaralé major verze (React < 17, React Router < 6, webpack < 5)
- Podezřelé, neudržované nebo typosquatting balíčky
- Chybějící security balíčky (DOMPurify pokud se používá dangerouslySetInnerHTML)
- Rizikové import patterny (CDN, dynamické importy z user inputu)
- Příliš volné version ranges (`"*"`, `">=0.0.0"`)
- Licenční rizika (GPL v komerčních projektech)

### 📋 Code Quality
Kontroluje obecnou kvalitu kódu:
- Chybějící ErrorBoundary komponenty kolem kritických sekcí UI
- Chybějící error handling v async operacích (fetch/axios bez try/catch)
- Memory leaky (chybějící cleanup v useEffect — event listenery, subscriptions, timery)
- Prop drilling hlubší než 3 úrovně
- Performance anti-patterny (inline objekty v JSX props, chybějící React.memo/useMemo/useCallback)
- Accessibility (chybějící alt, aria-label, non-semantic HTML, keyboard navigation)
- console.log v produkčním kódu
- Magic strings/numbers bez pojmenovaných konstant
- Komponenty delší než ~200 řádků

### ⚛️ React Specialist
Hloubková kontrola React-specific patterns:
- Porušení Rules of Hooks (podmíněné volání, hooks v loopu, chybějící dependency array)
- State management (přímá mutace stavu, derived state uložená jako state, useReducer vs useState)
- Component design (God components, chybějící separation of concerns, index jako key v listech)
- React 18+ patterns (chybějící Suspense, chybějící useTransition, StrictMode side effects)
- Context API misuse (Context s příliš častými změnami, chybějící memoizace value)

### 🔷 TypeScript Auditor
Hloubková kontrola TypeScript type safety:
- Konfigurace tsconfig.json (strict mode, noImplicitAny, strictNullChecks, noUncheckedIndexedAccess)
- Porušení type safety (explicitní `any`, unsafe `as` assertions, non-null `!` assertions)
- `@ts-ignore` a `@ts-expect-error` skrývající reálné problémy
- Chybějící nebo slabé typy (untyped parametry, untyped API responses, chybějící generika)
- React + TypeScript specifika (FC<Props> bez Props interface, untyped event handlers, useRef generika)
- Enum a union type usage (magic strings vs string literal unions)

### 🤝 Collaboration (React ↔ TypeScript)
Není samostatný agent — je to cross-review fáze:
- React Specialist přečte výstup TypeScript Auditora a najde průniky (hooks bez typů, untyped Context)
- TypeScript Auditor přečte výstup React Specialisty a doplní TS perspektivu (any v event handlerech, missing JSX types)
- Oba cross-reviews běží paralelně
- Výsledkem jsou doplňky ke stávajícím reportům, ne nové reporty

### 📝 Report Generator
Kompiluje finální report (bez přístupu k souborům — jen píše):
- Shrnutí s celkovým hodnocením rizika a počtem nálezů podle severity
- Bezpečnostní nálezy (Security + Dependency)
- Kvalita kódu
- React patterns (včetně collaboration průniků)
- TypeScript (včetně collaboration průniků)
- Prioritizovaná doporučení (top 5–10 věcí k opravě)
- Závěr s celkovým hodnocením projektu

## Klíčové koncepty

### Structured Output (Orchestrátor)
Orchestrátor vrací inventář v pevném JSON formátu. Příklad pro velký projekt:
```json
{
  "strategy": "modular",
  "file_count": 247,
  "has_typescript": true,
  "has_package_json": true,
  "modules": {
    "components": ["src/Button.tsx", "src/Modal.tsx", "..."],
    "hooks": ["src/useAuth.ts", "src/useForm.ts", "..."],
    "pages": ["src/pages/Home.tsx", "src/pages/Profile.tsx", "..."],
    "api": ["src/api/users.ts", "src/api/products.ts", "..."]
  },
  "summary": "React 18 projekt s TypeScriptem, 247 zdrojových souborů v monorepo struktuře."
}
```

### Swarm Pattern (Fáze 2)
Pět agentů běží současně přes `anyio.create_task_group()`. Každý dostane task prompt přizpůsobený strategii z inventáře — buď volný přístup nebo konkrétní seznam souborů. Sdílený slovník výsledků je chráněn `anyio.Lock()`.

### Collaboration Pattern (Fáze 3)
React a TypeScript domény se překrývají — typování hooks, generika v komponentách, `any` v event handlerech je problém obou světů najednou. Místo dalšího skenování kódu si agenti předají navzájem své výstupy (zkrácené na 3000 znaků) a napíší krátký supplement report zachycující průniky. Oba cross-reviews běží paralelně.

### Adaptive Strategy (Orchestrátor)
Klíčová inovace oproti původnímu projektu. Orchestrátor přizpůsobí hloubku skenování velikosti projektu:
- **free**: agent dostane volný přístup a sám rozhodne co číst (funguje pro malé projekty)
- **modular**: agent dostane předpřipravený seznam souborů rozdělený do logických modulů (zajistí pokrytí i na velkých projektech)

## Instalace a spuštění

### Požadavky
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Claude Code nainstalovaný (`curl -fsSL https://claude.ai/install.sh | bash`)
- Anthropic Pro/Max subskripce (Claude Code vyžaduje)

### Setup

```bash
git clone https://github.com/PavlinaBrz/react-security-audit.git
cd react-security-audit

uv venv
source .venv/bin/activate
uv sync
```

### Spuštění

```bash
# Audit konkrétního projektu
uv run python main.py /cesta/k/react-projektu

# Audit aktuální složky
uv run python main.py
```

### Ukázkový výstup

```
======================================================================
🛡️  REACT & TYPESCRIPT COMPREHENSIVE AUDIT
======================================================================

   Projekt: /home/user/my-react-app
   Čas:     2026-05-05 14:30

   Orchestrace (Swarm architektura):
     • Inventář      — Orchestrátor zmapuje projekt
     • Swarm         — 5 agentů skenuje paralelně
     • Collaboration — React ↔ TypeScript cross-review
     • Sequential    — kompilace finálního reportu

======================================================================
🗺️  FÁZE 1: INVENTÁŘ PROJEKTU (Orchestrátor)
======================================================================

   Nalezeno souborů:  247
   Strategie:         MODULAR
   TypeScript:        ano
   package.json:      ano
   Popis:             React 18 projekt s TypeScriptem, 247 souborů.

   Moduly (6):
     • components: 48 souborů
     • hooks: 23 souborů
     • pages: 31 souborů
     • api: 18 souborů
     • store: 12 souborů
     • utils: 19 souborů

======================================================================
🐝 FÁZE 2: SWARM — 5 agentů skenuje paralelně
======================================================================
   Spouštím všech 5 agentů současně...

   ▶ 🔒 Security Scanner — spuštěn
   ▶ 📦 Dependency Auditor — spuštěn
   ▶ 📋 Code Quality — spuštěn
   ▶ ⚛️  React Specialist — spuštěn
   ▶ 🔷 TypeScript Auditor — spuštěn
    🔧 🔒 Security Scanner → Glob
    🔧 ⚛️  React Specialist → Read
    🔧 🔷 TypeScript Auditor → Read
    ...
   ✅ 📦 Dependency Auditor — dokončen (2103 znaků)
   ✅ 📋 Code Quality — dokončen (3841 znaků)
   ✅ 🔒 Security Scanner — dokončen (4290 znaků)
   ✅ ⚛️  React Specialist — dokončen (5120 znaků)
   ✅ 🔷 TypeScript Auditor — dokončen (4780 znaků)

   Všech 5 agentů dokončilo skenování.

======================================================================
🤝 FÁZE 3: COLLABORATION — React ↔ TypeScript cross-review
======================================================================
   ▶ React Specialist — čte TypeScript audit...
   ▶ TypeScript Auditor — čte React audit...
   ✅ React Specialist — collaboration doplněk (891 znaků)
   ✅ TypeScript Auditor — collaboration doplněk (743 znaků)

======================================================================
📝 FÁZE 4: GENEROVÁNÍ REPORTU (Sequential)
======================================================================

======================================================================
✅ AUDIT DOKONČEN
======================================================================

   📄 Report uložen:   /home/user/my-react-app/audit_report_20260505_143012.md
   🐝 Agenti:          5 (parallel Swarm)
   🤝 Collaboration:   React ↔ TypeScript
   📊 Celkem analýzy:  21 134 znaků
   🗂️  Strategie:       MODULAR
   📁 Souborů v proj.: 247
```

## Struktura projektu

```
react-security-audit/
├── main.py            # Celý audit — Orchestrátor + Swarm + Collaboration + Report
├── pyproject.toml     # Závislosti (claude-agent-sdk, anyio)
├── README.md          # Tento soubor
└── .gitignore
```

## Funkce v main.py

| Funkce | Vzor | Popis |
|--------|------|-------|
| `run_agent()` | helper | Spustí jednoho agenta v izolované ClaudeSDKClient session |
| `run_orchestrator()` | Sequential + Structured output | Inventář projektu, volba strategie |
| `build_agent_prompt()` | helper | Sestaví task prompt podle strategie (free / modular) |
| `run_swarm()` | Parallel | 5 agentů paralelně, anyio.Lock() pro výsledky |
| `run_collaboration()` | Collaboration | React ↔ TS cross-review, běží paralelně |
| `generate_report()` | Sequential | Kompilace finálního Markdown reportu |
| `run_audit()` | pipeline | Hlavní flow spojující všechny 4 fáze |

## Technické poznámky

- Používá **Claude Agent SDK** (`claude-agent-sdk`) — Python SDK pro programatické ovládání Claude Code
- Každý agent běží ve vlastní izolované `ClaudeSDKClient` session (vlastní kontext, vlastní history)
- Orchestrátor i agenti čtou soubory přes vestavěné tools (Glob, Read, Grep)
- Orchestrátor rozhoduje přes **Structured output** (JSON schema) — stejný princip jako původní Supervisor
- Sdílené slovníky výsledků jsou chráněny `anyio.Lock()` ve všech paralelních fázích
- Collaboration fáze nepotřebuje tools — pracuje jen s texty (výstupy agentů)
- Report Generator dostane max. **4000 znaků** z každého reportu — pro kompilaci stačí přehled
- Collaboration cross-review dostane max. **3000 znaků** — pro hledání průniků stačí kratší kontext
- `node_modules` je explicitně vyloučen z inventáře i z validace zdrojových souborů

## Srovnání s původní architekturou

| Oblast | Původní (Supervisor + Loop) | Nová (Swarm) |
|--------|----------------------------|--------------|
| Agenti | 3 (Security, QA, Deps) | 5 (+ React, TypeScript) |
| Orchestrace | Supervisor hodnotí a opakuje | Orchestrátor mapuje a rozděluje |
| Pokrytí velkých projektů | agent hledá sám | modular strategie s mapou souborů |
| Průniky domén | žádné | Collaboration (React ↔ TS) |
| Opakování | Loop max 2× | žádné — vsázíme na kvalitu promptů |
| Fáze | 3 (Parallel, Supervisor+Loop, Report) | 4 (Inventář, Swarm, Collaboration, Report) |

## Autor
Pavlína
