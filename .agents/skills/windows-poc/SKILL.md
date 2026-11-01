---
name: windows-poc
description: Homologar offline a POC BuscaInsta no Windows 11, com setup reproduzível, 100 contatos sintéticos, testes negativos, logs agregados e evidência sem dados pessoais. Use para validação local antes de merge.
---

# Windows POC — verificação reproduzível

1. Ler `AGENTS.md` e `docs/AGENT_WORKFLOW.md`; inspecionar `git status --short` e branch; não descartar mudanças existentes.
2. Execute no PowerShell a partir da raiz: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1`.
3. Rode **novamente** o mesmo comando. Ambos devem finalizar com exit code 0. Instalação de pacote usa rede PyPI/GitHub somente para dependências públicas, não faz upload de contatos.
4. Validar `python -m pytest -q` no venv e inspeção dos cenários de entrada vazia, 101 linhas, cabeçalho duplicado, IDs repetidos, telefone/e-mail inválidos e ausência de consentimento.
5. Confirmar `git status --short` sem CSVs/segredos versionados; verificar em `git diff --check`.
6. Apresentar resumo **sem dados pessoais**: versão Windows/Python, commit, comandos/exit codes, testes, cobertura dos cenários, link de CI e riscos remanescentes.
7. Se houver erro, corrigir apenas o escopo mínimo com teste de regressão; manter PR Draft, sem login ou busca de usuários Instagram.

**STOP**: nenhum passo deste skill exporta contatos do CRM, autentica em Instagram ou faz correspondência reversa. Relatório de testes não comprova descoberta de @.
