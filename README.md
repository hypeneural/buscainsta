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

## Teste experimental online com um voluntário conhecido

Há também um **probe opcional da API não oficial** `instagrapi`: executa `address_book_link` com **um contato autorizado por execução**, compara a lista de sugestões com um `@username` previamente informado pelo próprio voluntário e tenta `address_book_unlink` ao terminar. É a primeira verificação real da hipótese de sincronização, mas **não prova identidade nem fornece busca reversa garantida**. Não é executada pelos testes ou pelo setup padrão.

Use **conta de teste sua, sem agenda previamente sincronizada**, não a conta comercial do estúdio. O uso da API privada pode violar condições da plataforma e gerar bloqueios; revise os termos e obtenha as autorizações necessárias antes de executar.

```powershell
py -3.12 -m venv .venv-live
.\.venv-live\Scripts\python.exe -m pip install -e ".[live]"
# Configure BUSCAINSTA_IG_TEST_LOGIN e BUSCAINSTA_IG_TEST_PASSWORD
# localmente, sem registrar valores no Git, no chat ou em screenshots.
.\.venv-live\Scripts\python.exe -m buscainsta.live_probe --input "C:\BuscaInstaPrivado\voluntario.csv" --contact-id VOL-001 --expected-username perfil_conhecido --confirm-contact-sharing
```

O comando nunca salva ou imprime nomes de perfis retornados: informa somente se o username esperado apareceu, número de sugestões e se a desconexão foi concluída. **Não execute 100 uploads em sequência**; primeiro determine se o mecanismo realmente funciona e se seu uso é permitido. Veja [protocolo de campo](docs/REAL_MVP.md).

## Painel local: foto, seguidores, confirmação e Direct

Implementado um painel local com botões de revisão e Direct individual, SQLite privado e foto de perfil. Veja [docs/DASHBOARD.md](docs/DASHBOARD.md). O painel não faz envios automáticos nem grava dados de clientes no GitHub.

## Unificação com o painel_conferencia.html existente

O antigo relatório estático com **2.739 linhas**, candidatos e filtros VIP pode ser importado de forma **somente leitura**, sem substituí-lo:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dashboard-windows.ps1 -Db "C:\BuscaInstaPrivado\buscainsta.db" -LegacyPanel "C:\BuscaInstaPrivado\painel_conferencia.html" -Account "estudio_teste"
```
Depois abra `http://127.0.0.1:8765/`. O painel unificado mantém rank, score e filtros e adiciona foto/follow, checkbox e Direct individual. Veja `docs/DASHBOARD.md`. Não fazer commit do HTML antigo: contém informações de clientes.
