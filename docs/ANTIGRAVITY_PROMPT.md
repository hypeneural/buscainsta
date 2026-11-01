# Prompt operacional para Antigravity — POC BuscaInsta Windows

Você é responsável por homologar a **fase offline** da PR #1 em `hypeneural/buscainsta`, branch `feat/windows-offline-poc-bootstrap`. Não inicie integração com o CRM ou Instagram.

1. Leia `AGENTS.md`, `docs/AGENT_WORKFLOW.md`, `docs/PLAN.md`, e a skill `.agents/skills/windows-poc/SKILL.md`. Confirme `git status -sb`, HEAD, alterações locais e PR. Não sobrescreva trabalhos pendentes.
2. Verifique Git e Python >=3.11 e execute no PowerShell:
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1`
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -SkipInstall`
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows.ps1`
3. Cada execução deve terminar com exit code 0. O verificador deve executar `doctor`, todos os testes pytest, gerar 100 registros fictícios e reportar validação 100/100, sem escrita persistente de dados pessoais.
4. Audite os testes negativos do pytest: CSV vazio, >100, duplicados, incompletos, cabeçalho errado, UTF-8 inválido, contato inválido, consentimento ausente, marcadores sintéticos falsos, saída sanitizada.
5. Se um teste falhar: identificar causa com arquivo/linha e comando, corrigir cirurgicamente, atualizar teste e executar novamente. Não descartar mudanças locais, não usar force-push, não fazer merge, não alterar a main nem outros repositórios.
6. Confira a CI da SHA final (Windows Python 3.11/3.12 e Ubuntu 3.11/3.12) e `git diff --check` e `git status`. O CI não comprova o ambiente Avell local.
7. Entregue um dossiê curto: OS/Python, branch/SHA, comandos e códigos de saída, resultado unitário e de 100 registros, regressões, CI por link, achados P0/P1/P2 e recomendação GO/NO-GO **somente para a POC offline**. Não copiar nome de cliente, telefones, e-mails, CSVs, tokens ou cookies.

STOP: esta fase não descobre @Instagram. Não acessar CRM de produção, exportar clientes, fazer login no Instagram, sincronizar agendas, testar APIs privadas, enviar dados para serviços, contornar bloqueios ou automatizar consultas de identidade. Qualquer fase com dados reais e acesso externo requer análise/consentimento e aprovação separada.
