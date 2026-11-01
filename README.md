# BuscaInsta — POC offline de contatos (Windows)

Projeto inicial para estudar a possibilidade de vincular, com autorização, perfis Instagram a contatos do CRM. **Não é um localizador de usernames por telefone/e-mail**. A API pública da Meta não disponibiliza essa busca reversa; relatos de bibliotecas privadas não comprovam correspondência confiável nem autorização de uso.

## Começar no Windows 11

Requer Python 3.11+ e Git. No PowerShell:

```powershell
git clone https://github.com/hypeneural/buscainsta.git
cd buscainsta
powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
```

O script instala apenas o aplicativo local e pytest. Gera `data/synthetic.csv` (100 contatos fictícios) e valida tudo **offline**.

Para executar manualmente:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m buscainsta.cli sample --out data/synthetic.csv --count 100
.\.venv\Scripts\python.exe -m buscainsta.cli validate --input data/synthetic.csv --synthetic
```

Nenhuma credencial Instagram, token Meta ou acesso ao CRM é requerido.

## Privacidade e escopo

- Repositório público: **não suba CSVs reais**, senhas, cookies ou relatórios pessoais.
- Não faça upload de dados de clientes a APIs privadas do Instagram. Dados do CRM para atendimento não pressupõem consentimento para descoberta de perfis.
- A validação de registros reais é **somente local**, exige consentimento específico e não efetua lookup no Instagram.
- Resultados agregados não identificam clientes.
- Veja [plano detalhado](docs/PLAN.md) e [instruções do Antigravity](docs/ANTIGRAVITY_PROMPT.md).

## Fontes técnicas estudadas

- https://github.com/subzeroid/instagrapi
- https://github.com/subzeroid/aiograpi
- https://github.com/dilame/instagram-private-api

As bibliotecas acima são referências de pesquisa, não dependências instaladas nem garantias de funcionamento atual.
