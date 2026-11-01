# Prompt operacional — Antigravity no Windows

Use o repositório `hypeneural/buscainsta`, branch `feat/windows-offline-poc-bootstrap`, PR #1 Draft e issue #2.

1. Leia `AGENTS.md`, `docs/AGENT_WORKFLOW.md` e `docs/PLAN.md`. Inspecione `git status -sb`, `git branch --show-current`, `git log -3 --oneline`. Não sobrescreva arquivos locais nem use outra branch sem necessidade.
2. Faça um plano curto (`/plan` se suportado) para homologar a fase offline; leia `.agents/skills/windows-poc/SKILL.md` e execute os passos.
3. No PowerShell, rode `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1` **duas vezes**. Verifique exit code de cada execução, testes pytest, geração/validação de 100 exemplos sintéticos e retorno sem dados pessoais.
4. Faça testes negativos de cabeçalho duplicado, CSV vazio, mais de 100 registros, ID duplicado, formatos inválidos e ausência de consentimento. Verifique `git diff --check` e dados indevidos em `git status`.
5. Revise a PR com o skill `/review-pr` e, se disponível, agente `offline-reviewer`. Qualquer bug deve ter patch pequeno, teste e commit na própria branch; não faça merge/force-push/deploy.
6. Entregue SHA da branch, versões Windows/Python, comandos e códigos de saída, resultados dos testes, URL da run GitHub Actions da **SHA final**, achados P0/P1/P2 e checklist de gates.
7. **Não** acessar CRM de produção, dados reais, autenticar no Instagram, sincronizar agenda, usar APIs privadas, proxies, scraping ou publicar PII. Se alguma dessas tarefas parecer necessária, pare e solicite aprovação específica. Não afirme que encontra usernames reais.

A POC não faz chamadas externas para Instagram/CRM; instalação de dependências pode acessar fontes públicas como PyPI. O objetivo é reproduzir localmente o POC offline com logs agregados.
