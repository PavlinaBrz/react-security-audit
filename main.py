#!/usr/bin/env python3
"""
React Security Audit Pipeline
==============================

Multi-agent orchestration for automated security auditing of React projects.

Demonstrates three orchestration patterns:
  1. SUPERVISOR (multi-agent) — Audit Supervisor coordinates the team,
     decides when results are sufficient or need more work
  2. PARALLEL (workflow) — Three specialist agents scan the project simultaneously:
     Security Scanner, Code Quality Reviewer, Dependency Auditor
  3. LOOP (workflow) — If Supervisor finds gaps in any agent's report,
     it sends that agent back to deepen the analysis (max 2 re-runs)

At the end, a Report Generator compiles everything into a Markdown report.

Usage:
    uv run python main.py /path/to/react-project
    uv run python main.py                          # uses current directory
"""

import argparse
import re
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
# Spustí jednoho agenta ve vlastní izolované session (vlastní ClaudeSDKClient).
# Každý agent má vlastní kontext — přesně jako v lektorových ukázkách.
# ==============================================================================

async def run_agent(
    name: str,
    system_prompt: str,
    prompt: str,
    tools: list[str] | None = None,
    cwd: str | None = None,
) -> str:
    """Spustí jednoho agenta v izolované session a vrátí jeho textovou odpověď.

    Každý agent dostane svůj vlastní ClaudeSDKClient — izolovaný kontext,
    vlastní tools a pracovní složku. Přesně jako lektorovy ukázky ze single_agent.

    Args:
        name: Jméno agenta (pro výpis do konzole)
        system_prompt: Systémový prompt — role a chování agenta
        prompt: Úkol pro agenta
        tools: Seznam povolených tools (např. ["Read", "Bash", "Glob", "Grep"])
        cwd: Pracovní složka agenta (cesta k React projektu)

    Returns:
        Textová odpověď agenta
    """
    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=system_prompt,
        allowed_tools=tools or [],
    )

    # Nastavíme pracovní složku, aby agent četl soubory z React projektu
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
# PARALLEL WORKFLOW — tři specializovaní agenti běží najednou
# ==============================================================================
# Fan-out: Spustíme tři agenty paralelně (anyio.create_task_group)
# Fan-in: Sesbíráme výsledky do slovníku
#
# Proč parallel a ne sequential? Protože agenti na sobě nezávisí — každý
# kontroluje jinou věc. Ušetříme čas. (Lekce 5 — Parallel workflow)
# ==============================================================================

# System prompty pro jednotlivé agenty
SECURITY_SCANNER_PROMPT = """You are a React security specialist. Your job is to scan React source code
for security vulnerabilities. Focus on:

1. XSS vulnerabilities (dangerouslySetInnerHTML, unescaped user input in JSX)
2. Hardcoded secrets (API keys, tokens, passwords in source code)
3. Insecure API calls (HTTP instead of HTTPS, missing auth headers)
4. Unsafe eval() or Function() usage
5. Prototype pollution risks
6. Insecure localStorage/sessionStorage usage for sensitive data
7. Missing CSRF protection
8. Open redirects

For each finding, provide:
- SEVERITY: CRITICAL / HIGH / MEDIUM / LOW
- FILE: which file contains the issue
- LINE: approximate line number if possible
- DESCRIPTION: what the issue is
- RECOMMENDATION: how to fix it

Write your report in Czech. Be thorough but factual — only report real issues you find in the code."""

CODE_QUALITY_PROMPT = """You are a React code quality expert. Your job is to review React source code
for quality issues and bad practices. Focus on:

1. Missing error boundaries (ErrorBoundary components)
2. Missing error handling in async operations (fetch, axios without try/catch)
3. Prop types validation (missing TypeScript types or PropTypes)
4. Memory leaks (missing cleanup in useEffect, unsubscribed event listeners)
5. Performance anti-patterns (unnecessary re-renders, missing React.memo/useMemo/useCallback)
6. Accessibility issues (missing alt on images, missing aria labels, non-semantic HTML)
7. Hardcoded strings that should be in config/env
8. Console.log left in production code

For each finding, provide:
- SEVERITY: HIGH / MEDIUM / LOW
- FILE: which file contains the issue
- DESCRIPTION: what the issue is
- RECOMMENDATION: how to fix it

Write your report in Czech. Be specific — reference actual files and code patterns you find."""

DEPENDENCY_AUDITOR_PROMPT = """You are a dependency security auditor. Your job is to analyze the project's
dependencies for security risks.

First, check if package.json exists. If yes, analyze it. If not, analyze import statements
in source files to identify which packages are used.

Focus on:
1. Known vulnerable packages (check version numbers against known CVEs)
2. Outdated major versions of critical packages (React, React Router, webpack, etc.)
3. Suspicious or unknown packages
4. Missing security-related packages (helmet, cors, csp headers)
5. Risky import patterns (importing from CDN, dynamic imports from user input)
6. If no package.json is present, list all third-party imports found in source code
   and flag any that are known to have security issues

For each finding, provide:
- SEVERITY: CRITICAL / HIGH / MEDIUM / LOW
- PACKAGE: which package
- DESCRIPTION: what the risk is
- RECOMMENDATION: what to do

Write your report in Czech. Only report issues you actually find."""


async def run_parallel_scan(project_path: str) -> dict[str, str]:
    """Spustí tři agenty paralelně a vrátí jejich výsledky.

    Toto je PARALLEL WORKFLOW (fan-out / fan-in pattern).
    Všichni tři agenti čtou soubory z React projektu současně,
    každý se zaměřuje na jinou oblast.

    Args:
        project_path: Cesta k React projektu

    Returns:
        Slovník {agent_name: report_text}
    """
    print("\n" + "=" * 70)
    print("📡 FÁZE 1: PARALELNÍ SKENOVÁNÍ (Parallel Workflow)")
    print("=" * 70)
    print("   Spouštím 3 agenty současně...")

    # Společné tools — agenti potřebují číst soubory projektu
    scan_tools = ["Read", "Glob", "Grep"]

    # Společný task prompt — liší se jen system prompt (= role agenta)
    scan_prompt = f"""Scan this React project and provide a detailed audit report.

Project path: {project_path}

Steps:
1. First use Glob to discover the project structure (find *.jsx, *.tsx, *.js, *.ts files)
2. If package.json exists, read it to understand dependencies. If not, skip this step.
3. Read the key source files and analyze them according to your specialty
4. Compile your findings into a structured report

Be thorough. Check all relevant files, not just a few.
Note: package.json may not be present — if so, focus on analyzing source code only."""

    # Definice agentů pro paralelní běh
    agents = [
        ("🔒 Security Scanner", SECURITY_SCANNER_PROMPT),
        ("📋 Code Quality", CODE_QUALITY_PROMPT),
        ("📦 Dependency Auditor", DEPENDENCY_AUDITOR_PROMPT),
    ]

    results: dict[str, str] = {}

    async with anyio.create_task_group() as tg:

        async def scan_and_collect(name: str, sys_prompt: str) -> None:
            print(f"\n   ▶ {name} — spuštěn")
            result = await run_agent(
                name=name,
                system_prompt=sys_prompt,
                prompt=scan_prompt,
                tools=scan_tools,
                cwd=project_path,
            )
            results[name] = result
            print(f"   ✅ {name} — dokončen ({len(result)} znaků)")

        for name, sys_prompt in agents:
            tg.start_soon(scan_and_collect, name, sys_prompt)

    print(f"\n   Všichni 3 agenti dokončili skenování.")
    return results


# ==============================================================================
# SUPERVISOR + LOOP — kontrola kvality a případné doplnění
# ==============================================================================
# Supervisor přečte výsledky od všech tří agentů a rozhodne:
# - Jsou výsledky kompletní? → pokračuj na report
# - Některý agent byl příliš vágní? → pošli ho zpět (LOOP)
#
# Structured output řídí rozhodování supervisora. (Lekce 3/5)
# ==============================================================================

SUPERVISOR_SCHEMA = {
    "type": "object",
    "properties": {
        "all_complete": {
            "type": "boolean",
            "description": "true pokud jsou všechny reporty dostatečně detailní a kompletní",
        },
        "incomplete_agent": {
            "type": "string",
            "description": "Jméno agenta, jehož report potřebuje doplnit (pokud all_complete=false)",
        },
        "feedback": {
            "type": "string",
            "description": "Co konkrétně má agent doplnit nebo zlepšit (pokud all_complete=false)",
        },
        "summary": {
            "type": "string",
            "description": "Krátké shrnutí stavu auditu pro výpis do konzole",
        },
    },
    "required": ["all_complete", "summary"],
    "additionalProperties": False,
}

SUPERVISOR_PROMPT = """You are the Audit Supervisor. You coordinate a security audit of a React project.
You do NOT scan code yourself. You review the reports from your team of specialists and decide
if the audit is complete.

Your team:
- 🔒 Security Scanner: checks for XSS, hardcoded secrets, insecure API calls
- 📋 Code Quality: checks for error handling, performance, accessibility
- 📦 Dependency Auditor: checks package.json for vulnerable dependencies

Review each report and decide:
- If all reports are thorough and specific (reference actual files, provide actionable recommendations),
  set all_complete=true
- If any report is too vague, too short, or missing important checks, set all_complete=false
  and specify which agent needs to do more work and what exactly they should improve

Be strict about quality. A good report should reference specific files and line numbers,
not just list general best practices."""


async def run_supervisor_review(
    scan_results: dict[str, str],
    project_path: str,
    max_loops: int = 2,
) -> dict[str, str]:
    """Supervisor kontroluje kvalitu reportů a případně posílá agenty zpět.

    Toto kombinuje SUPERVISOR PATTERN (multi-agent) + LOOP WORKFLOW.
    Supervisor rozhoduje přes structured output. Pokud některý report
    není dostatečný, agent dostane zpětnou vazbu a zkusí to znovu.

    Args:
        scan_results: Výsledky z paralelního skenování
        project_path: Cesta k React projektu
        max_loops: Maximální počet opakování pro jednoho agenta

    Returns:
        Finální (případně vylepšené) výsledky
    """
    print("\n" + "=" * 70)
    print("🎯 FÁZE 2: SUPERVISOR REVIEW + LOOP (Supervisor + Loop)")
    print("=" * 70)

    # Mapování jmen agentů na jejich system prompty (pro případný re-run)
    agent_prompts = {
        "🔒 Security Scanner": SECURITY_SCANNER_PROMPT,
        "📋 Code Quality": CODE_QUALITY_PROMPT,
        "📦 Dependency Auditor": DEPENDENCY_AUDITOR_PROMPT,
    }

    final_results = dict(scan_results)  # kopie, budeme případně přepisovat
    loop_count = 0

    while loop_count < max_loops:
        loop_count += 1
        print(f"\n   📋 Supervisor review — iterace {loop_count}/{max_loops}")

        # Připravíme přehled reportů pro supervisora
        reports_overview = ""
        for agent_name, report in final_results.items():
            # Zkrátíme report na prvních 2000 znaků pro supervisor kontext
            truncated = report[:2000] + ("..." if len(report) > 2000 else "")
            reports_overview += f"\n\n### {agent_name}\n{truncated}"

        # Supervisor rozhodne přes structured output
        options = ClaudeAgentOptions(
            model="sonnet",
            system_prompt=SUPERVISOR_PROMPT,
            output_format={
                "type": "json_schema",
                "schema": SUPERVISOR_SCHEMA,
            },
        )

        supervisor_prompt = f"""Review the following audit reports from your team.
Decide if they are all complete and detailed enough, or if any agent needs to improve their report.

{reports_overview}"""

        decision = None
        async for msg in query(prompt=supervisor_prompt, options=options):
            if isinstance(msg, ResultMessage):
                if msg.structured_output:
                    decision = msg.structured_output
                if msg.total_cost_usd and msg.total_cost_usd > 0:
                    print(f"    💰 Supervisor: ${msg.total_cost_usd:.4f}")

        if decision is None:
            print("    ⚠️  Supervisor nevrátil rozhodnutí, pokračuji dál.")
            break

        print(f"    📝 {decision.get('summary', '')}")

        # Pokud je vše kompletní, končíme loop
        if decision.get("all_complete", True):
            print("    ✅ Supervisor: Všechny reporty jsou kompletní.")
            break

        # Pokud ne — LOOP: pošleme agenta zpět s feedbackem
        incomplete = decision.get("incomplete_agent", "")
        feedback = decision.get("feedback", "")

        if not incomplete or incomplete not in agent_prompts:
            print(f"    ⚠️  Neznámý agent '{incomplete}', pokračuji dál.")
            break

        print(f"    🔄 Loop: posílám '{incomplete}' zpět s feedbackem:")
        print(f"       \"{feedback[:100]}...\"")

        # Re-run agenta s původním + feedbackovým promptem
        rerun_prompt = f"""You previously scanned this React project and produced this report:

{final_results[incomplete]}

Your supervisor found the report insufficient. Their feedback:
{feedback}

Please re-scan the project at {project_path} and provide an IMPROVED, more detailed report.
Address the supervisor's feedback specifically. Use Glob, Read, and Grep to find more details."""

        improved_report = await run_agent(
            name=f"{incomplete} (re-run)",
            system_prompt=agent_prompts[incomplete],
            prompt=rerun_prompt,
            tools=["Read", "Glob", "Grep"],
            cwd=project_path,
        )

        final_results[incomplete] = improved_report
        print(f"    ✅ {incomplete} — vylepšený report ({len(improved_report)} znaků)")

    return final_results


# ==============================================================================
# REPORT GENERATOR — Sequential krok na konci pipeline
# ==============================================================================

REPORT_GENERATOR_PROMPT = """You are a technical report writer. Compile the audit findings from
multiple specialists into a single, well-structured Markdown security audit report.

The report should have these sections:
1. **Shrnutí** — executive summary with overall risk assessment (CRITICAL/HIGH/MEDIUM/LOW)
2. **Bezpečnostní nálezy** — findings from the security scanner
3. **Kvalita kódu** — findings from the code quality reviewer
4. **Závislosti** — findings from the dependency auditor
5. **Doporučení** — prioritized action items (what to fix first)
6. **Závěr** — overall assessment

Use Czech language. Format the report with proper Markdown headers, bullet points,
and severity badges. Make it professional and actionable.

Start the report with:
# 🛡️ Bezpečnostní audit — React projekt
"""


async def generate_report(
    results: dict[str, str],
    project_path: str,
) -> str:
    """Vygeneruje finální Markdown report ze všech nálezů.

    Toto je SEQUENTIAL krok — následuje po Parallel + Supervisor/Loop fázích.
    Report Generator dostane výsledky od všech agentů a zkompiluje je.

    Args:
        results: Finální výsledky od všech agentů
        project_path: Cesta k projektu (pro metadata v reportu)

    Returns:
        Markdown text reportu
    """
    print("\n" + "=" * 70)
    print("📝 FÁZE 3: GENEROVÁNÍ REPORTU (Sequential)")
    print("=" * 70)

    # Sestavíme vstup pro report generátora
    all_findings = ""
    for agent_name, report in results.items():
        all_findings += f"\n\n## Findings from {agent_name}:\n{report}"

    report_prompt = f"""Compile the following specialist audit findings into a unified Markdown report.

Project: {project_path}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

{all_findings}

Create a comprehensive, well-organized report in Czech."""

    report = await run_agent(
        name="📝 Report Generator",
        system_prompt=REPORT_GENERATOR_PROMPT,
        prompt=report_prompt,
        tools=[],  # Report generator nepotřebuje tools — jen píše
    )

    return report


# ==============================================================================
# MAIN PIPELINE — spojuje všechny 3 orchestrace dohromady
# ==============================================================================

async def run_audit(project_path: str) -> None:
    """Spustí celý audit pipeline.

    Flow:
        1. PARALLEL — 3 agenti skenují projekt současně
        2. SUPERVISOR + LOOP — supervisor kontroluje kvalitu, případně vrací agenty
        3. SEQUENTIAL — report generator zkompiluje finální report

    Args:
        project_path: Absolutní cesta k React projektu
    """
    print("=" * 70)
    print("🛡️  REACT SECURITY AUDIT PIPELINE")
    print("=" * 70)
    print(f"\n   Projekt: {project_path}")
    print(f"   Čas:     {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\n   Orchestrace:")
    print(f"     • Parallel workflow  — 3 agenti skenují současně")
    print(f"     • Supervisor pattern — kontrola kvality výsledků")
    print(f"     • Loop workflow      — iterativní vylepšení (max 2×)")
    print(f"     • Sequential         — kompilace finálního reportu")

    # --- Fáze 1: Paralelní skenování ---
    scan_results = await run_parallel_scan(project_path)

    # --- Fáze 2: Supervisor review + Loop ---
    reviewed_results = await run_supervisor_review(scan_results, project_path)

    # --- Fáze 3: Generování reportu ---
    report = await generate_report(reviewed_results, project_path)

    # --- Uložení reportu ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"audit_report_{timestamp}.md"
    report_path = Path(project_path) / report_filename

    report_path.write_text(report, encoding="utf-8")

    print("\n" + "=" * 70)
    print("✅ AUDIT DOKONČEN")
    print("=" * 70)
    print(f"\n   📄 Report uložen: {report_path}")
    print(f"   📊 Skenováno agenty: 3 (parallel)")
    print(f"   🎯 Supervisor review: ano")
    print(f"   📝 Formát: Markdown")
    print()


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    """Vstupní bod — zpracuje argumenty a spustí pipeline."""
    parser = argparse.ArgumentParser(
        description="🛡️ React Security Audit Pipeline — multi-agent orchestration demo"
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Cesta k React projektu (default: aktuální složka)",
    )

    args = parser.parse_args()

    # Resolve na absolutní cestu
    project_path = str(Path(args.project_path).resolve())

    # Základní kontrola — existuje složka a obsahuje zdrojové soubory?
    if not Path(project_path).is_dir():
        print(f"⚠️  Složka '{project_path}' neexistuje.")
        sys.exit(1)

    # Hledáme jakékoliv React/TS/JS soubory
    source_extensions = (".tsx", ".jsx", ".ts", ".js")
    has_sources = any(
        f.suffix in source_extensions
        for f in Path(project_path).rglob("*")
        if f.is_file()
    )
    if not has_sources:
        print(f"⚠️  V '{project_path}' nebyly nalezeny žádné zdrojové soubory (.tsx, .jsx, .ts, .js).")
        print(f"   Jste ve správné složce?")
        sys.exit(1)

    print(f"✅ Nalezeny zdrojové soubory v '{project_path}'")

    anyio.run(run_audit, project_path)


if __name__ == "__main__":
    main()