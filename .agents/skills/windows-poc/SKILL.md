---
name: windows-poc
description: Executar a homologação local offline BuscaInsta no Windows 11 com testes pytest e 100 registros sintéticos, repetibilidade, privacidade e evidências de CI. Use antes de qualquer merge.
---

# Homologação Windows — sequência obrigatória

1. Ler `AGENTS.md`, `docs/AGENT_WORKFLOW.md`, inspecionar `git status -sb`, `git log -3 --oneline` e branch da PR #1. Não descartar mudanças locais.
2. Rodar `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1` (primeiro setup; pip pode baixar dependências **públicas**).
3. Rodar `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -SkipInstall` (segunda execução, sem reinstalar pacotes).
4. Rodar `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows.ps1` e `.\.venv\Scripts\python.exe -m buscainsta.cli doctor`. Exigir exit code zero e sumário 100/100. O verificador usa arquivo temporário e apaga no final.
5. Validar pytest negativo: linha 101, CSV vazio/incompleto, cabeçalho duplicado, ID duplicado, e-mail/telefone inválidos, consentimento faltante, sintético com e-mail não reservado e UTF-8 inválido.
6. Executar `git diff --check`, checar que nenhum arquivo de contato real/segredo é rastreado (`git ls-files`) e conferir execução do GitHub Actions na **SHA final**.
7. Relatar somente dados agregados: comando, código de saída, SHA, versões do Windows/Python, CI e achados P0/P1/P2. Falha em gate significa NO-GO até correção; manter PR Draft.

**Parada obrigatória**: sem acesso ao CRM, sem login Meta/Instagram, sem sincronização, scraping ou correspondência reversa real. O pipeline offline não demonstra descoberta de perfis.
