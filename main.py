#!/usr/bin/env python3
"""
React & TypeScript Comprehensive Audit — Swarm Architecture
=============================================================

Kompletní audit React projektů přes tým 5 specializovaných AI agentů.

Orchestrace:
  1. INVENTÁŘ    — Orchestrátor zmapuje projekt, zvolí strategii podle velikosti
  2. SWARM       — 5 agentů skenuje paralelně (fan-out / fan-in)
  3. COLLABORATION — React a TypeScript agenti si předají kontext (průniky domén)
  4. SEQUENTIAL  — Report Generator zkompiluje finální Markdown report

Agenti:
  🔒 Security Scanner   — XSS, secrets, CSRF, insecure storage
  📦 Dependency Auditor — CVE, zastaralé balíčky, licenční rizika
  📋 Code Quality       — error handling, memory leaky, accessibility
  ⚛️  React Specialist  — hooks rules, patterns, kompozice komponent
  🔷 TypeScript Auditor — strict config, any, generika, type safety

Usage:
    uv run python main.py /cesta/k/react-projektu
    uv run python main.py                          # aktuální složka
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import anyio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)


# ==============================================================================
# HELPER: run_agent
# ==============================================================================
# Každý agent běží ve vlastní izolované ClaudeSDKClient session.
# Vlastní kontext, vlastní tools, vlastní pracovní složka.
# ==============================================================================

async def run_agent(
    name: str,
    system_prompt: str,
    prompt: str,
    tools: list[str] | None = None,
    cwd: str | None = None,
) -> str:
    """Spustí jednoho agenta v izolované session a vrátí jeho textovou odpověď.

    Args:
        name: Jméno agenta (pro výpis do konzole)
        system_prompt: Systémový prompt definující roli a chování agenta
        prompt: Konkrétní úkol pro agenta
        tools: Seznam povolených nástrojů (Read, Glob, Grep)
        cwd: Pracovní složka — kořen auditovaného projektu

    Returns:
        Textová odpověď agenta (report nebo rozhodnutí)
    """
    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=system_prompt,
        allowed_tools=tools or [],
    )
    if cwd:
        options.cwd = cwd

    result_parts: list[str] = []

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        result_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        print(f"    🔧 {name} → {block.name}")
            elif isinstance(msg, ResultMessage):
                if msg.total_cost_usd and msg.total_cost_usd > 0:
                    print(f"    💰 {name}: ${msg.total_cost_usd:.4f}")

    return "\n".join(result_parts)


# ==============================================================================
# SYSTEM PROMPTY — definice rolí všech 5 agentů
# ==============================================================================

SECURITY_SCANNER_PROMPT = """You are a React security specialist. Scan React source code
for security vulnerabilities. Focus on:

1. XSS vulnerabilities (dangerouslySetInnerHTML, unescaped user input in JSX)
2. Hardcoded secrets (API keys, tokens, passwords directly in source code)
3. Insecure API calls (HTTP instead of HTTPS, missing auth headers)
4. Unsafe eval() or Function() constructor usage
5. Prototype pollution risks
6. Insecure localStorage/sessionStorage usage for sensitive data
7. Missing CSRF protection in forms and API mutations
8. Open redirects (unvalidated redirect targets)
9. Unsafe use of window.postMessage without origin validation
10. Content Security Policy violations or missing CSP

For each finding provide:
- SEVERITY: CRITICAL / HIGH / MEDIUM / LOW
- FILE: which file
- LINE: approximate line number if possible
- DESCRIPTION: what the issue is and why it's dangerous
- RECOMMENDATION: concrete fix

Write your report in Czech. Be thorough but factual — only report real issues found in code.
If you find no issues in a category, state that explicitly."""


DEPENDENCY_AUDITOR_PROMPT = """You are a dependency security auditor. Analyze the project's
dependencies for security and maintenance risks.

Start by reading package.json (and package-lock.json if present). If package.json doesn't exist,
analyze import statements across all source files to identify used packages.

Focus on:
1. Known vulnerable packages — check version ranges against known CVEs for React ecosystem
2. Critically outdated major versions (React < 17, React Router < 6, webpack < 5, etc.)
3. Suspicious, unmaintained, or typosquatting packages
4. Missing security-relevant packages (e.g. DOMPurify for sanitization if dangerouslySetInnerHTML is used)
5. Risky import patterns (CDN imports, dynamic imports constructed from user input)
6. Packages with overly broad version ranges (e.g. "*" or ">=0.0.0")
7. License risks (GPL in commercial projects, unlicensed packages)

For each finding provide:
- SEVERITY: CRITICAL / HIGH / MEDIUM / LOW
- PACKAGE: package name and current version
- DESCRIPTION: what the risk is
- RECOMMENDATION: what to do (update, replace, remove)

Write your report in Czech. Only report issues you actually find."""


CODE_QUALITY_PROMPT = """You are a React code quality expert. Review React source code
for quality issues, bad practices, and maintainability problems. Focus on:

1. Missing ErrorBoundary components around critical UI sections
2. Missing error handling in async operations (fetch/axios without try/catch/finally)
3. Memory leaks: missing cleanup in useEffect (event listeners, subscriptions, timers)
4. Prop drilling deeper than 3 levels (suggest Context or state management)
5. Performance anti-patterns: inline object/array literals in JSX props causing re-renders,
   missing React.memo on expensive components, missing useMemo/useCallback
6. Accessibility: missing alt on images, missing aria-label, non-semantic HTML,
   missing keyboard navigation support
7. console.log / console.error left in production code
8. Hardcoded magic strings/numbers that should be constants or config
9. Components longer than ~200 lines (single responsibility violation)
10. Inconsistent naming conventions (mixing camelCase and PascalCase for components)

For each finding provide:
- SEVERITY: HIGH / MEDIUM / LOW
- FILE: which file
- DESCRIPTION: what the issue is
- RECOMMENDATION: how to fix it

Write your report in Czech. Reference specific files and code patterns you find."""


REACT_SPECIALIST_PROMPT = """You are a React patterns and best practices specialist.
Perform a deep review of React-specific code quality. Focus on:

1. Rules of Hooks violations:
   - Hooks called conditionally or inside loops
   - Hooks called outside React function components
   - Missing or incorrect dependency arrays in useEffect, useMemo, useCallback

2. State management issues:
   - Direct state mutation instead of setState
   - State that should be derived (computed from other state) stored separately
   - Overuse of useState where useReducer would be clearer
   - Global state anti-patterns (excessive prop drilling, missing Context)

3. Component design:
   - God components (mixing data fetching, business logic, and rendering)
   - Missing separation of concerns (hooks for logic, components for rendering)
   - Incorrect use of key prop in lists (using index as key where items reorder)
   - Overuse of useEffect where event handlers would be simpler

4. React 18+ patterns:
   - Missing Suspense boundaries for async data or lazy-loaded components
   - Missing transitions for non-urgent updates (useTransition, startTransition)
   - Incorrect use of StrictMode side effects

5. Context API misuse:
   - Context that changes too frequently causing full subtree re-renders
   - Missing context value memoization

For each finding provide:
- SEVERITY: HIGH / MEDIUM / LOW
- FILE: which file
- PATTERN: which React pattern is violated
- DESCRIPTION: what the issue is
- RECOMMENDATION: the correct React pattern to use

Write your report in Czech. Be specific — reference hooks, component names, and line numbers."""


TYPESCRIPT_AUDITOR_PROMPT = """You are a TypeScript strict-mode specialist. Perform a deep
audit of TypeScript usage quality. Focus on:

1. TypeScript configuration (tsconfig.json):
   - Is strict mode enabled? (strict: true)
   - Are dangerous options enabled? (noImplicitAny, strictNullChecks, strictFunctionTypes)
   - Is skipLibCheck masking real errors?
   - Missing noUncheckedIndexedAccess for array safety

2. Type safety violations:
   - Explicit `any` usage (each instance is a type safety hole)
   - `as` type assertions without validation (casting away type errors)
   - Non-null assertions (!) hiding potential null/undefined errors
   - `@ts-ignore` and `@ts-expect-error` comments hiding real issues

3. Missing or weak types:
   - Untyped function parameters and return values
   - Untyped API responses (using `any` instead of proper interfaces)
   - Missing generics where code is duplicated for different types
   - `object` or `{}` used instead of specific interface

4. React + TypeScript specific:
   - Missing or incorrect prop type definitions (FC<Props> without Props interface)
   - Untyped event handlers (MouseEvent<HTMLButtonElement> etc.)
   - Missing return type on components (JSX.Element | null)
   - Incorrect typing of useRef (useRef<HTMLDivElement>(null) pattern)

5. Enum and union type usage:
   - Magic strings where string literal unions would be safer
   - Numeric enums where string enums would be more debuggable

For each finding provide:
- SEVERITY: HIGH / MEDIUM / LOW
- FILE: which file
- LINE: approximate line if possible
- ISSUE: what TypeScript rule is violated
- DESCRIPTION: why this is a problem
- RECOMMENDATION: the type-safe alternative

Write your report in Czech. Be precise — TypeScript issues need exact file and type information."""


# ==============================================================================
# FÁZE 1: ORCHESTRÁTOR — inventář projektu a strategie skenování
# ==============================================================================
# Orchestrátor zmapuje projekt a rozhodne:
#   < 100 souborů → agenti dostanou volný přístup, hledají sami
#   ≥ 100 souborů → Orchestrátor sestaví mapu modulů, přiřadí agentům soubory
#
# Tím eliminujeme riziko, že agent přečte jen prvních 20 souborů a zbytek ignoruje.
# ==============================================================================

ORCHESTRATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "strategy": {
            "type": "string",
            "enum": ["free", "modular"],
            "description": (
                "'free' pokud má projekt < 100 zdrojových souborů — agenti hledají sami. "
                "'modular' pokud má projekt >= 100 souborů — soubory jsou rozděleny do modulů."
            ),
        },
        "file_count": {
            "type": "integer",
            "description": "Celkový počet nalezených zdrojových souborů (.tsx, .jsx, .ts, .js)",
        },
        "modules": {
            "type": "object",
            "description": (
                "Pouze při strategy='modular'. "
                "Mapování oblast → seznam relativních cest souborů. "
                "Příklad: {'components': ['src/Button.tsx', ...], 'hooks': ['src/useAuth.ts', ...]}"
            ),
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "has_typescript": {
            "type": "boolean",
            "description": "true pokud projekt obsahuje .ts nebo .tsx soubory",
        },
        "has_package_json": {
            "type": "boolean",
            "description": "true pokud projekt obsahuje package.json",
        },
        "summary": {
            "type": "string",
            "description": "Krátký popis nalezené struktury projektu (1-2 věty)",
        },
    },
    "required": ["strategy", "file_count", "has_typescript", "has_package_json", "summary"],
    "additionalProperties": False,
}

ORCHESTRATOR_PROMPT = """You are a project orchestrator. Your job is to analyze a React project's
structure and decide the best scanning strategy for the audit team.

Steps:
1. Use Glob to find all source files (*.tsx, *.jsx, *.ts, *.js) — exclude node_modules
2. Count the total number of source files
3. Check if package.json exists
4. Check if there are .ts or .tsx files (TypeScript project)
5. Decide strategy:
   - 'free': fewer than 100 source files — agents will explore independently
   - 'modular': 100 or more files — group files into logical modules by directory/feature

If strategy is 'modular', group files into modules by their directory structure.
Use meaningful module names like 'components', 'hooks', 'pages', 'utils', 'api', 'store', etc.
Each module should have 10-30 files. Split large directories into sub-modules if needed.

Return ONLY the structured JSON — no additional text."""


async def run_orchestrator(project_path: str) -> dict:
    """Spustí Orchestrátora — zmapuje projekt a vrátí strategii skenování.

    Toto je FÁZE 1 Swarm architektury. Orchestrátor není supervisor —
    nehodnotí kvalitu, jen mapuje strukturu a rozděluje práci.

    Args:
        project_path: Absolutní cesta k React projektu

    Returns:
        Slovník se strategií a případnou mapou modulů
    """
    print("\n" + "=" * 70)
    print("🗺️  FÁZE 1: INVENTÁŘ PROJEKTU (Orchestrátor)")
    print("=" * 70)

    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=ORCHESTRATOR_PROMPT,
        allowed_tools=["Glob"],
        output_format={"type": "json_schema", "schema": ORCHESTRATOR_SCHEMA},
    )
    options.cwd = project_path

    inventory_prompt = f"""Analyze the React project at: {project_path}

Use Glob to find all source files. Exclude node_modules, .git, dist, build directories.
Then return the structured inventory."""

    inventory = None
    async for msg in query(prompt=inventory_prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.structured_output:
                inventory = msg.structured_output

    if inventory is None:
        # Fallback — pokud structured output selže, použijeme free strategii
        print("   ⚠️  Orchestrátor nevrátil strukturovaný výstup, používám 'free' strategii.")
        return {
            "strategy": "free",
            "file_count": 0,
            "has_typescript": True,
            "has_package_json": True,
            "summary": "Inventář se nezdařil, agenti prohledají projekt samostatně.",
        }

    strategy = inventory.get("strategy", "free")
    file_count = inventory.get("file_count", 0)
    print(f"\n   Nalezeno souborů:  {file_count}")
    print(f"   Strategie:         {strategy.upper()}")
    print(f"   TypeScript:        {'ano' if inventory.get('has_typescript') else 'ne'}")
    print(f"   package.json:      {'ano' if inventory.get('has_package_json') else 'ne'}")
    print(f"   Popis:             {inventory.get('summary', '')}")

    if strategy == "modular":
        modules = inventory.get("modules", {})
        print(f"\n   Moduly ({len(modules)}):")
        for mod_name, files in modules.items():
            print(f"     • {mod_name}: {len(files)} souborů")

    return inventory


def build_agent_prompt(
    project_path: str,
    inventory: dict,
    agent_focus: str,
) -> str:
    """Sestaví task prompt pro agenta podle zvolené strategie.

    Args:
        project_path: Cesta k projektu
        inventory: Výsledek Orchestrátora
        agent_focus: Krátký popis zaměření agenta (pro kontext v promptu)

    Returns:
        Task prompt připravený pro agenta
    """
    strategy = inventory.get("strategy", "free")
    has_ts = inventory.get("has_typescript", True)
    has_pkg = inventory.get("has_package_json", True)

    base = f"""Perform a thorough audit of this React project focused on: {agent_focus}

Project path: {project_path}
TypeScript project: {"yes" if has_ts else "no"}
package.json present: {"yes" if has_pkg else "no"}
"""

    if strategy == "free":
        return base + """
Instructions:
1. Use Glob to discover the full project structure (*.tsx, *.jsx, *.ts, *.js — exclude node_modules)
2. Read package.json if it exists
3. Read and analyze ALL relevant source files — do not stop after a few files
4. Compile your findings into a structured report

Be thorough. Read every file that could be relevant to your specialty."""

    else:
        modules = inventory.get("modules", {})
        module_list = "\n".join(
            f"  - {name}: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}"
            for name, files in modules.items()
        )
        return base + f"""
The project has been divided into these modules:
{module_list}

Instructions:
1. Read package.json if it exists
2. Work through EACH module — read the files listed above
3. Use Grep to search for specific patterns across the project when needed
4. Compile your findings into a structured report covering ALL modules

Do not skip any module. This is a large project — be systematic."""


# ==============================================================================
# FÁZE 2: SWARM — 5 agentů skenuje paralelně
# ==============================================================================
# Fan-out: všech 5 agentů spuštěno najednou přes anyio.create_task_group()
# Fan-in: výsledky sesbírány do slovníku chráněného anyio.Lock()
#
# Agenti jsou rozděleni do dvou domén:
#   Bezpečnostní: Security Scanner, Dependency Auditor
#   Kvalitativní: Code Quality, React Specialist, TypeScript Auditor
# ==============================================================================

async def run_swarm(project_path: str, inventory: dict) -> dict[str, str]:
    """Spustí všech 5 agentů paralelně — Swarm pattern (fan-out / fan-in).

    Každý agent dostane task prompt přizpůsobený strategii z inventáře.
    Výsledky jsou chráněny anyio.Lock() při zápisu do sdíleného slovníku.

    Args:
        project_path: Cesta k projektu
        inventory: Výsledek Orchestrátora (strategie + modul mapa)

    Returns:
        Slovník {agent_name: report_text}
    """
    print("\n" + "=" * 70)
    print("🐝 FÁZE 2: SWARM — 5 agentů skenuje paralelně")
    print("=" * 70)
    print("   Spouštím všech 5 agentů současně...\n")

    scan_tools = ["Read", "Glob", "Grep"]

    # Definice agentů: (jméno, system_prompt, popis zaměření pro task prompt)
    agents = [
        (
            "🔒 Security Scanner",
            SECURITY_SCANNER_PROMPT,
            "security vulnerabilities (XSS, secrets, CSRF, insecure storage, open redirects)",
        ),
        (
            "📦 Dependency Auditor",
            DEPENDENCY_AUDITOR_PROMPT,
            "dependency security (CVE, outdated packages, license risks, risky imports)",
        ),
        (
            "📋 Code Quality",
            CODE_QUALITY_PROMPT,
            "code quality (error handling, memory leaks, performance, accessibility)",
        ),
        (
            "⚛️  React Specialist",
            REACT_SPECIALIST_PROMPT,
            "React-specific patterns (hooks rules, component design, state management, Suspense)",
        ),
        (
            "🔷 TypeScript Auditor",
            TYPESCRIPT_AUDITOR_PROMPT,
            "TypeScript type safety (strict config, any usage, missing types, generics)",
        ),
    ]

    results: dict[str, str] = {}
    results_lock = anyio.Lock()

    async with anyio.create_task_group() as tg:

        async def scan_and_collect(
            name: str,
            sys_prompt: str,
            focus: str,
        ) -> None:
            print(f"   ▶ {name} — spuštěn")
            prompt = build_agent_prompt(project_path, inventory, focus)
            result = await run_agent(
                name=name,
                system_prompt=sys_prompt,
                prompt=prompt,
                tools=scan_tools,
                cwd=project_path,
            )
            async with results_lock:
                results[name] = result
            print(f"   ✅ {name} — dokončen ({len(result)} znaků)")

        for agent_name, agent_prompt, agent_focus in agents:
            tg.start_soon(scan_and_collect, agent_name, agent_prompt, agent_focus)

    print(f"\n   Všech 5 agentů dokončilo skenování.")
    return results


# ==============================================================================
# FÁZE 3: COLLABORATION — React a TypeScript agenti si předají kontext
# ==============================================================================
# React a TypeScript domény se překrývají:
#   - typování hooks (useRef<HTMLDivElement>, useState<User[]>)
#   - generika v komponentách (FC<Props>)
#   - `any` v event handlerech jako React i TS problém
#
# Každý agent dostane výstup toho druhého a doplní průniky.
# Tím získáme hlubší nálezy bez dalšího skenování kódu.
# ==============================================================================

REACT_COLLABORATION_PROMPT = """You are a React patterns specialist reviewing your own findings
in light of the TypeScript audit. Your goal is to identify issues that span both React and TypeScript.

Focus on:
1. Hooks with missing or incorrect TypeScript types (useRef without generic, useState inferred as never)
2. Component props that lack TypeScript interfaces — find specific components from the React audit
   that also have type issues mentioned in the TypeScript audit
3. Event handlers in React components that use `any` or are untyped
4. React patterns made worse by missing TypeScript (e.g. untyped Context values)
5. Any React issues from your original report that the TypeScript audit confirms or deepens

Write a SHORT supplement report in Czech — only NEW insights from the cross-review.
Do not repeat findings already in your original report.
Start with: ## Průniky React a TypeScript"""


TYPESCRIPT_COLLABORATION_PROMPT = """You are a TypeScript specialist reviewing your own findings
in light of the React audit. Your goal is to identify issues that span both TypeScript and React.

Focus on:
1. TypeScript `any` usage specifically in React hooks, components, or context
2. Missing generics that would make React patterns safer (generic form hooks, typed context)
3. Type assertions (`as`) used to work around React prop type mismatches
4. TypeScript config issues that mask React-specific bugs (e.g. skipLibCheck hiding JSX issues)
5. Missing or incorrect JSX types (wrong JSX.Element return type, missing ReactNode)

Write a SHORT supplement report in Czech — only NEW insights from the cross-review.
Do not repeat findings already in your original report.
Start with: ## Průniky TypeScript a React"""


async def run_collaboration(swarm_results: dict[str, str]) -> dict[str, str]:
    """Spustí collaboration fázi — React a TS agenti si přečtou navzájem výstupy.

    Toto je COLLABORATION pattern. Agenti nekontrolují znovu kód — pracují
    s výstupy od sebe navzájem a hledají průniky svých domén.

    Args:
        swarm_results: Výsledky ze Swarm fáze

    Returns:
        Aktualizovaný slovník s doplněnými collaboration výstupy
    """
    print("\n" + "=" * 70)
    print("🤝 FÁZE 3: COLLABORATION — React ↔ TypeScript cross-review")
    print("=" * 70)

    react_report = swarm_results.get("⚛️  React Specialist", "")
    ts_report = swarm_results.get("🔷 TypeScript Auditor", "")

    MAX_CHARS = 3000  # Pro collaboration stačí přehled, ne celý report

    react_truncated = react_report[:MAX_CHARS] + ("..." if len(react_report) > MAX_CHARS else "")
    ts_truncated = ts_report[:MAX_CHARS] + ("..." if len(ts_report) > MAX_CHARS else "")

    collaboration_results = dict(swarm_results)
    collab_lock = anyio.Lock()

    async def react_cross_review() -> None:
        print("   ▶ React Specialist — čte TypeScript audit...")
        prompt = f"""Here is your original React audit report:

{react_truncated}

Here is the TypeScript audit from your colleague:

{ts_truncated}

Now write your cross-review supplement."""

        supplement = await run_agent(
            name="⚛️  React (collaboration)",
            system_prompt=REACT_COLLABORATION_PROMPT,
            prompt=prompt,
            tools=[],  # Collaboration nepotřebuje tools — pracuje s texty
        )
        async with collab_lock:
            collaboration_results["⚛️  React Specialist"] = react_report + "\n\n" + supplement
        print(f"   ✅ React Specialist — collaboration doplněk ({len(supplement)} znaků)")

    async def ts_cross_review() -> None:
        print("   ▶ TypeScript Auditor — čte React audit...")
        prompt = f"""Here is your original TypeScript audit report:

{ts_truncated}

Here is the React patterns audit from your colleague:

{react_truncated}

Now write your cross-review supplement."""

        supplement = await run_agent(
            name="🔷 TypeScript (collaboration)",
            system_prompt=TYPESCRIPT_COLLABORATION_PROMPT,
            prompt=prompt,
            tools=[],
        )
        async with collab_lock:
            collaboration_results["🔷 TypeScript Auditor"] = ts_report + "\n\n" + supplement
        print(f"   ✅ TypeScript Auditor — collaboration doplněk ({len(supplement)} znaků)")

    # Oba cross-reviews běží paralelně — nezávisí na sobě
    async with anyio.create_task_group() as tg:
        tg.start_soon(react_cross_review)
        tg.start_soon(ts_cross_review)

    return collaboration_results


# ==============================================================================
# FÁZE 4: REPORT GENERATOR — Sequential kompilace finálního reportu
# ==============================================================================

REPORT_GENERATOR_PROMPT = """You are a technical report writer specializing in React project audits.
Compile the findings from 5 specialist agents into a single, comprehensive Markdown report.

The report MUST have these sections in order:
1. **Shrnutí** — executive summary, celkové hodnocení rizika (CRITICAL/HIGH/MEDIUM/LOW),
   počet nálezů podle severity
2. **Bezpečnostní nálezy** — ze Security Scanner a Dependency Auditor
3. **Kvalita kódu** — z Code Quality agenta
4. **React patterns** — z React Specialist (včetně collaboration průniků)
5. **TypeScript** — z TypeScript Auditor (včetně collaboration průniků)
6. **Prioritizovaná doporučení** — top 5-10 věcí k opravě seřazených od nejkritičtějšího
7. **Závěr** — celkové hodnocení projektu

Use Czech language throughout. Format with proper Markdown headers, bullet points, and code blocks.
Use severity badges: 🔴 CRITICAL, 🟠 HIGH, 🟡 MEDIUM, 🟢 LOW.
Make it professional, actionable, and specific — reference actual files and patterns.

Start the report with:
# 🛡️ Komplexní audit — React & TypeScript projekt
"""


async def generate_report(results: dict[str, str], project_path: str) -> str:
    """Zkompiluje finální Markdown report ze všech agentů.

    Toto je SEQUENTIAL fáze — přichází po Swarm + Collaboration.
    Report Generator dostane souhrn od všech 5 agentů a sestaví report.

    Args:
        results: Finální výsledky (po collaboration) od všech agentů
        project_path: Cesta k projektu (pro metadata)

    Returns:
        Markdown text finálního reportu
    """
    print("\n" + "=" * 70)
    print("📝 FÁZE 4: GENEROVÁNÍ REPORTU (Sequential)")
    print("=" * 70)

    # Každý report zkrátíme na 4000 znaků — generátor potřebuje přehled
    MAX_REPORT_CHARS = 4000
    all_findings = ""
    for agent_name, report in results.items():
        truncated = report[:MAX_REPORT_CHARS] + (
            f"\n\n[... zkráceno z {len(report)} na {MAX_REPORT_CHARS} znaků ...]"
            if len(report) > MAX_REPORT_CHARS else ""
        )
        all_findings += f"\n\n## Findings from {agent_name}:\n{truncated}"

    report_prompt = f"""Compile the following audit findings into a unified Markdown report.

Project: {project_path}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Agents: Security Scanner, Dependency Auditor, Code Quality, React Specialist, TypeScript Auditor

{all_findings}

Create a comprehensive, professional report in Czech covering all five audit domains."""

    report = await run_agent(
        name="📝 Report Generator",
        system_prompt=REPORT_GENERATOR_PROMPT,
        prompt=report_prompt,
        tools=[],  # Nepotřebuje přístup k souborům — jen kompiluje texty
    )

    return report


# ==============================================================================
# HLAVNÍ PIPELINE — spojuje všechny 4 fáze
# ==============================================================================

async def run_audit(project_path: str) -> None:
    """Spustí kompletní audit pipeline — Swarm architektura.

    Flow:
        1. Orchestrátor   → inventář + strategie skenování
        2. Swarm          → 5 agentů paralelně (fan-out / fan-in)
        3. Collaboration  → React ↔ TypeScript cross-review
        4. Sequential     → Report Generator zkompiluje finální report

    Args:
        project_path: Absolutní cesta k React projektu
    """
    print("=" * 70)
    print("🛡️  REACT & TYPESCRIPT COMPREHENSIVE AUDIT")
    print("=" * 70)
    print(f"\n   Projekt: {project_path}")
    print(f"   Čas:     {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\n   Orchestrace (Swarm architektura):")
    print(f"     • Inventář      — Orchestrátor zmapuje projekt")
    print(f"     • Swarm         — 5 agentů skenuje paralelně")
    print(f"     • Collaboration — React ↔ TypeScript cross-review")
    print(f"     • Sequential    — kompilace finálního reportu")

    # --- Fáze 1: Inventář ---
    inventory = await run_orchestrator(project_path)

    # --- Fáze 2: Swarm ---
    swarm_results = await run_swarm(project_path, inventory)

    # --- Fáze 3: Collaboration ---
    final_results = await run_collaboration(swarm_results)

    # --- Fáze 4: Report ---
    report = await generate_report(final_results, project_path)

    # --- Uložení ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"audit_report_{timestamp}.md"
    report_path = Path(project_path) / report_filename
    report_path.write_text(report, encoding="utf-8")

    # Souhrn do konzole
    total_chars = sum(len(r) for r in final_results.values())
    print("\n" + "=" * 70)
    print("✅ AUDIT DOKONČEN")
    print("=" * 70)
    print(f"\n   📄 Report uložen:   {report_path}")
    print(f"   🐝 Agenti:          5 (parallel Swarm)")
    print(f"   🤝 Collaboration:   React ↔ TypeScript")
    print(f"   📊 Celkem analýzy:  {total_chars:,} znaků")
    print(f"   🗂️  Strategie:       {inventory.get('strategy', '?').upper()}")
    print(f"   📁 Souborů v proj.: {inventory.get('file_count', '?')}")
    print()


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main() -> None:
    """Vstupní bod — zpracuje CLI argumenty a spustí audit."""
    parser = argparse.ArgumentParser(
        description="🛡️ React & TypeScript Comprehensive Audit — Swarm multi-agent architecture"
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Cesta k React projektu (default: aktuální složka)",
    )
    args = parser.parse_args()

    project_path = str(Path(args.project_path).resolve())

    if not Path(project_path).is_dir():
        print(f"⚠️  Složka '{project_path}' neexistuje.")
        sys.exit(1)

    source_extensions = (".tsx", ".jsx", ".ts", ".js")
    has_sources = any(
        f.suffix in source_extensions
        for f in Path(project_path).rglob("*")
        if f.is_file() and "node_modules" not in f.parts
    )
    if not has_sources:
        print(f"⚠️  V '{project_path}' nebyly nalezeny žádné zdrojové soubory.")
        print(f"   Hledám: {', '.join(source_extensions)}")
        print(f"   Jste ve správné složce?")
        sys.exit(1)

    print(f"✅ Projekt nalezen: {project_path}")
    anyio.run(run_audit, project_path)


if __name__ == "__main__":
    main()