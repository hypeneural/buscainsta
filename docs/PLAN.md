# Plano cirúrgico — Windows / Antigravity

## Escopo autorizado agora
- Sem acesso à produção, sem API Instagram, sem sessão privada, sem upload de contatos ou extração de usernames.
- Importar **até 100 contatos locais** em CSV exclusivamente para normalização e validação consent-aware. Começar com amostra **100% sintética**.
- O arquivo CSV real, se um dia autorizado, deve permanecer só no computador do operador; **nunca** subir a GitHub, issues, CI ou logs.
- Consentimento explícito é obrigatório por registro real para o propósito de associação de contas Instagram. A posse dos dados no CRM para venda ou atendimento não equivale a essa autorização.

## Instalação no Windows 11
```powershell
git clone https://github.com/hypeneural/buscainsta.git
cd buscainsta
git switch feat/windows-offline-poc-bootstrap
powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
```
O script cria ambiente Python, executa testes e valida 100 registros fictícios. Não instala instagrapi/aiograpi porque não há execução externa autorizada nessa fase.

## Esquema CSV (UTF-8)
`contact_id,full_name,phone,email,instagram,consent,consent_date,consent_source`

- Dados reais: `consent=yes`, `consent_date=AAAA-MM-DD`, `consent_source` documenta o aceite, sob revisão.
- Telefones são normalizados de modo conservador para o padrão brasileiro; telefones internacionais/ambíguos são rejeitados. Validar regras adicionais antes de produção.
- O CLI não transmite os dados e retorna exclusivamente **contagens agregadas**; não grava nomes, telefones ou e-mails em relatórios.
- Não considerar username como confirmado só por sugestão, associação por nome ou `addressbook_name`.

## Sequência de execução
1. Inspecionar branch/PR e estado limpo do clone.
2. Executar script de instalação Windows.
3. Verificar pytest e os agregados 100/100 sintéticos.
4. Inspecionar .gitignore e verificar que nenhum CSV pessoal ou segredo está rastreado.
5. Opcional: carregar amostra **autorizada** com `python -m buscainsta.cli validate --input data/consented.csv`. O CSV fica apenas local. Para CSVs reais, consentimento precisa ser validado externamente e não apenas alegado em uma coluna.
6. Documentar erros, versões do Python, comandos e resultados agregados. Não publicar PII.
7. **STOP**: não adicionar conectores CRM/Meta/Instagram, sessões, token, upload ou busca automática sem revisão legal e aprovação explícita separada.

## Evidências mínimas
- Python 3.11+; pytest PASS no Windows; 100 linhas sintéticas importadas; `network_calls=0`; `external_uploads=0`.
- Entrada com linha 101, duplicatas, cabeçalho incorreto ou ausência de consentimento deve falhar ou sinalizar invalidez.
- Nenhuma alegação de correspondência Instagram: `instagram_lookup=not_implemented`.

## POC futura (não implementada)
- Levantar APIs oficiais Meta para interações **iniciadas pelos titulares** e inclusão voluntária de @instagram.
- Estudar bibliotecas não oficiais `instagrapi`, `aiograpi`, `instagram-private-api` apenas no código-fonte; sua capacidade de retornar um @ por telefone/e-mail não está comprovada em 2026.
- Um teste de plataforma só poderá ser concebido após análise de termos/privacidade e aprovação explícita, com contas e contatos consentidos; não automatizar descoberta de perfis privados, burlar controles, usar proxies para evasão ou recuperação de senha.
- Em eventual etapa futura, introduzir revisão humana e proveniência das associações antes de qualquer escrita no CRM.
