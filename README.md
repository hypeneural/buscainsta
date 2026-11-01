# BuscaInsta — MVP Windows para pesquisa e validação de perfis

**Situação:** validador offline homologado no Windows 11 (57 testes em `76345c6`); agora acrescentamos um **piloto de campo com contatos autorizados**, candidatos observados e confirmação pelo cliente. O piloto **não** tem busca reversa automática de username por telefone/e-mail.

## Instalação inicial (Windows 11)

Git e Python 3.11+:

```powershell
git clone https://github.com/hypeneural/buscainsta.git
cd buscainsta
git switch feat/windows-offline-poc-bootstrap
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
```

Ambiente já instalado: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -SkipInstall`.

## Teste real com até 100 contatos autorizados

Prepare manualmente um CSV UTF-8 de contatos com autorização específica **fora do clone Git**. Exemplo de caminho privado: `C:\\BuscaInstaPrivado\\contatos.csv`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_pilot.py
.\.venv\Scripts\python.exe -m buscainsta.cli validate --input "C:\\BuscaInstaPrivado\\contatos.csv" --local-consented
.\.venv\Scripts\python.exe -m buscainsta.pilot prepare --input "C:\\BuscaInstaPrivado\\contatos.csv" --output "C:\\BuscaInstaPrivado\\revisao.csv"
# Preencha manualmente candidatos, status e confirmação no CSV privado.
.\.venv\Scripts\python.exe -m buscainsta.pilot summarize --input "C:\\BuscaInstaPrivado\\revisao.csv"
```

O arquivo de revisão registra `pending`, `candidate`, `confirmed`, `not_found` ou `rejected`. Só confirme uma identidade quando a própria pessoa a confirmar. O programa **não** conecta ao Instagram/CRM, não faz scraping, não envia e-mail/WhatsApp e não guarda PII no GitHub. Os comandos exibem apenas totais agregados. O CSV privado pode conter identificadores, não compartilhe.

Veja: [guia completo do piloto](docs/REAL_MVP.md), [regras do agente](AGENTS.md), [skill real-pilot](.agents/skills/real-pilot/SKILL.md), [workflow](docs/AGENT_WORKFLOW.md), [prompt Antigravity](docs/ANTIGRAVITY_PROMPT.md), [contrato de validação](docs/VALIDATION_CONTRACT.md).

## Por que a API privada não está ativada por padrão?

A `instagrapi` documenta `address_book_link`, que envia contatos e pode retornar sugestões. Isso **não confirma associação individual** e envolve compartilhamento de contatos com a Meta, além de possíveis restrições de automação. Por isso o primeiro teste real compara observações e confirmações consentidas, sem prometer `telefone -> @`. Não há conexão de CRM produção.

Fontes: https://github.com/subzeroid/instagrapi ; https://antigravity.google/docs/skills ; https://antigravity.google/docs/rules/
