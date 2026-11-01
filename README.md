# BuscaInsta — POC offline Windows

Objetivo da fase P0: homologar um validador **local**, de até **100 contatos sintéticos com telefone vazio e e-mail reservado**. Não é uma ferramenta para descobrir perfis Instagram por telefone/e-mail. Não importa dados reais do CRM nem acessa serviços da Meta.

## Windows 11 (PowerShell)

Pré-requisitos: Git, Python 3.11+ instalado e disponível no PATH (ou launcher `py`), e internet **somente no primeiro setup** para baixar dependências de desenvolvimento.

```powershell
git clone https://github.com/hypeneural/buscainsta.git
cd buscainsta
git switch feat/windows-offline-poc-bootstrap
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
```

O instalador cria `.venv` no **próprio repositório**, instala o pacote/pytest e chama o verificador. O verificador executa `doctor`, pytest e valida **100 contatos fictícios** em arquivo temporário que é apagado ao terminar. Nenhum contato é enviado para a internet.

Depois da instalação, repita sem baixar dependências:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -SkipInstall
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows.ps1
.\.venv\Scripts\python.exe -m buscainsta.cli doctor
```

Os dois scripts devem retornar código 0. Se falharem, **não** declarar homologação: registrar somente erro técnico sanitizado, Python/Windows, branch e SHA, sem copiar arquivos locais de clientes.

### CLI manual

```powershell
.\.venv\Scripts\python.exe -m buscainsta.cli sample --out data/synthetic.csv --count 100
.\.venv\Scripts\python.exe -m buscainsta.cli validate --input data/synthetic.csv --synthetic
```

`sample` não sobrescreve arquivos existentes. O validador retorna resumo **agregado** em JSON; código 0 significa registros válidos, código 2 indica entrada inválida ou falha. É obrigatório selecionar **um dos modos**: `--synthetic` ou `--local-consented`. O segundo só valida dados autorizados no computador, jamais pesquisa Instagram. Cabeçalho exigido: `contact_id,full_name,phone,email,instagram,consent,consent_date,consent_source`. O modo `--synthetic` exige alinhamento exato entre ID, nome e e-mail gerados, **telefone/Instagram/data vazios**, `consent=test_only` e `consent_source=synthetic`; **isso não prova que os dados são fictícios**, portanto nunca alimentar com contatos reais.

### Antigravity

Leia `AGENTS.md`, `docs/AGENT_WORKFLOW.md` e use o skill `.agents/skills/windows-poc/SKILL.md`. O prompt completo está em `docs/ANTIGRAVITY_PROMPT.md`; a revisão na skill `.agents/skills/review-pr/SKILL.md`. Manter PR #1 em **Draft** até testes Windows locais e CI na SHA final.

## Segurança e escopo

Repositório **público**: nenhum CSV, nome, telefone, e-mail, token, cookie ou credencial de clientes no GitHub/CI. Coloque qualquer dado autorizado somente fora deste repositório, nunca em comentários ou logs. A coluna `consent=yes` é apenas um marcador e **não substitui comprovação de autorização**. Não acessar CRM/Instagram ou enviar contatos a APIs não oficiais nesta fase.

Bibliotecas `instagrapi`, `aiograpi`, `instagram-private-api` são referências **não instaladas**. Nenhuma correspondência @Instagram foi validada.

Links: [plano](docs/PLAN.md), [workflow](docs/AGENT_WORKFLOW.md), [skill](.agents/skills/windows-poc/SKILL.md), [PR #1](https://github.com/hypeneural/buscainsta/pull/1).

## Contrato atualizado e execução do Antigravity

- [Matriz forense de validadores e casos adversariais](docs/VALIDATION_CONTRACT.md).
- [Prompt de re-homologação após as alterações](docs/ANTIGRAVITY_PROMPT.md).
- A execução de 23 testes no SHA `cf84f615` corresponde à **versão anterior**, não valida os novos contratos; exigir CI + Windows local na SHA atual.
- `network_calls=0` é declarativo: **não constitui captura de tráfego**. Instalação de dependências via pip pode acessar a internet.
- Arquivos `*.egg-info/` gerados localmente em instalação editável são ignorados; nunca fazer commit de dados pessoais.
