# BuscaInsta — POC offline Windows

Projeto para estudar, com segurança e autorização, a associação de perfis Instagram a contatos do CRM. **Não implementa busca reversa de usuários por telefone/e-mail.** Bibliotecas não oficiais de sincronização de agenda não comprovaram correspondência confiável nem autorização da plataforma.

## Início rápido (Windows 11)

Requer Git e Python >=3.11 com launcher `py`. No PowerShell:

```powershell
git clone https://github.com/hypeneural/buscainsta.git
cd buscainsta
git switch feat/windows-offline-poc-bootstrap
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
```

Execute o último comando **duas vezes**: deve ter o mesmo resultado. Ele cria um venv, instala a aplicação e pytest, roda os testes e gera/valida **100 registros inteiramente fictícios** em um arquivo temporário, removido ao final. Pode baixar dependências de PyPI, mas **não conecta ao CRM nem ao Instagram**.

Teste manual local:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m buscainsta.cli sample --out data/synthetic.csv --count 100
.\.venv\Scripts\python.exe -m buscainsta.cli validate --input data/synthetic.csv --synthetic
```

O comando `sample` recusa sobrescrita; para repetir o exemplo manual, remova apenas o **seu CSV fictício** já existente ou use outro caminho. **Não exclua arquivos reais por engano.** A validação de CSV emite contagens agregadas e retorna código de saída 2 quando alguma linha é inválida. Cabeçalhos esperados: `contact_id,full_name,phone,email,instagram,consent,consent_date,consent_source`.

## Trabalho com o Antigravity

- [Regras persistentes do agente](AGENTS.md) — carregadas automaticamente.
- [Workflow e gates](docs/AGENT_WORKFLOW.md) — sequência canônica e evidências.
- [Skill /windows-poc](.agents/skills/windows-poc/SKILL.md) — homologar Windows.
- [Skill /review-pr](.agents/skills/review-pr/SKILL.md) — auditoria de PR.
- [Agente offline-reviewer](.agents/agents/offline-reviewer.md) — especialista em regressões e privacidade.
- [Prompt curto de execução](docs/ANTIGRAVITY_PROMPT.md) e [plano detalhado](docs/PLAN.md).

**A PR #1 permanece Draft** até que CI da SHA final e execução no Windows local sejam confirmados. Não faça merge ou deploy sem revisão.

## Privacidade

O repositório é público. Não faça commit de CSVs reais, telefones, e-mails, nomes de clientes, tokens, cookies ou logs pessoais. Dados reais, se alguma etapa futura os utilizar localmente, exigem consentimento específico para o propósito e nunca são enviados automaticamente a Instagram/Meta. O aceite registrado em uma coluna não comprova por si só autorização legal. Resultados de sugestões não confirmam identidades.

## Bibliotecas de referência (não instaladas)

- https://github.com/subzeroid/instagrapi
- https://github.com/subzeroid/aiograpi
- https://github.com/dilame/instagram-private-api

As APIs privadas acima **não integram esta POC**. A API oficial da Meta não oferece pesquisa reversa genérica por telefone/e-mail.
