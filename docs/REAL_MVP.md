# MVP real BuscaInsta — 100 contatos, Windows 11

## Objetivo mensurável

Usar até 100 contatos **com autorização específica para esta finalidade** para comparar hipóteses de descoberta: pesquisa nominal, sugestões no aplicativo Instagram mediante sincronização permitida e identificação diretamente fornecida pelo titular. O aplicativo `buscainsta.pilot` **não consulta Instagram nem faz busca reversa automática**. Ele permite um teste real, auditável, com humanos e arquivos locais.

Não impor o modo sintético aos contatos reais: no piloto local a opção é `--local-consented`. Registros sem consentimento específico devem ser excluídos da amostra, não presumidos válidos porque constam no CRM.

## Fonte de dados

Criar CSV UTF-8 em pasta privada **fora do clone Git**, por exemplo `C:\\BuscaInstaPrivado\\contatos.csv`. Formato:

```csv
contact_id,full_name,phone,email,instagram,consent,consent_date,consent_source
LOCAL-001,Pessoa Teste,,teste@example.invalid,,yes,2026-10-30,aceite_especifico
```

Este exemplo é sintético (e-mail reservado), serve apenas para ilustrar a estrutura. Um export real deve ser obtido de forma autorizada e mapeado localmente pelo operador; não conectar/alterar o CRM de produção automaticamente. O formato de origem real do CRM ainda não foi auditado. Se as colunas diferirem, criar adaptador local **sem enviar arquivos ao agente ou GitHub**.

## Passo a passo

1. No PowerShell do clone atualizado: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pilot.py`.
2. `.\.venv\Scripts\python.exe -m buscainsta.cli validate --input "C:\\BuscaInstaPrivado\\contatos.csv" --local-consented`.
3. `.\.venv\Scripts\python.exe -m buscainsta.pilot prepare --input "C:\\BuscaInstaPrivado\\contatos.csv" --output "C:\\BuscaInstaPrivado\\revisao.csv"`.
4. Abrir `revisao.csv` **somente localmente**. Campos: `contact_id,invite_code,candidate_username,discovery_method,status,confirmation_source`. A planilha de revisão **não copia** nome, telefone nem e-mail, mas ainda pode ser identificável, então deve ficar em pasta privada.
5. Registrar descoberta por `native_contact_suggestion`, `name_search`, `crm_existing`, `client_self_reported` ou `official_dm`. Exemplo: observar sugestões nativas com consentimento, anotar candidato e marcar `candidate`. **A sugestão não confirma a relação com o número/e-mail.**
6. Para confirmação, peça ao próprio cliente o `@username` por canal já autorizado; quando apropriado, inclua `invite_code` para o operador comparar manualmente à resposta recebida. Só então marcar `confirmed` e `confirmation_source=client_confirmed` (ou `client_self_reported` / `official_authorized_interaction`). O programa não lê conversas nem verifica automaticamente os códigos.
7. `.\.venv\Scripts\python.exe -m buscainsta.pilot summarize --input "C:\\BuscaInstaPrivado\\revisao.csv"`.
8. Compartilhar no GitHub **somente** totais: `reviewed`, `pending`, `candidates`, `confirmed`, `not_found`, `rejected`, `review_rate`, `confirmation_rate`.

## Métricas e decisão

- **Candidate rate** = candidatos ainda sem confirmação / total.
- **Confirmed rate** = confirmados pelo cliente / total.
- **Unresolved** = pendentes, não encontrados, rejeitados ou candidatos não confirmados.
- Para avaliar a hipótese telefone/e-mail -> Instagram, comparar 5–10 voluntários com @ previamente conhecido. Se sugestões não corresponderem individualmente à agenda, registrar **inconclusivo**, não `match`.
- A primeira meta é medir o processo e erros humanos; não inventar taxa de sucesso antes da amostra.

## Princípios práticos

- Não usar proxies, sessões compartilhadas, engenharia de recuperação de senha nem coleta automatizada privada.
- O Instagram pode não mostrar perfis sincronizados e pode misturar sugestões baseadas em outros sinais. O upload nativo de contatos compartilha dados com a Meta; analisar a autorização e o aviso aos titulares antes desse método.
- `invite_code` é referência operacional para conferência humana, **não** autenticação, assinatura eletrônica ou prova automática.
- Se houver candidatos falsos, revisar; nunca escrever @ automaticamente no CRM.
- O Windows não é um cofre por si: restrinja acesso à pasta privada e elimine os arquivos quando não necessários.
- PR/CI: somente fixtures fictícios. Nenhum acesso a Instagram é necessário para executar pytest.

## Experimento online opcional — telefone/e-mail → sugestão

Este experimento serve especificamente para responder se a implementação *atual* de `instagrapi.address_book_link` retorna uma sugestão contendo o @ já conhecido de um **único voluntário**. Não é ferramenta para localizar pessoas sem consentimento e não deve ser escalada automaticamente.

**Pré-condições:** (1) voluntário concordou expressamente com compartilhamento dos dados de contato à Meta; (2) conta de Instagram de teste própria, sem agenda vinculada; (3) aceitação dos riscos de bloqueio/termos da Meta e verificação de autorização de uso; (4) conhecimento antecipado do @ informado pelo voluntário; (5) nenhum dado do CRM em arquivos públicos.

Em venv separado `.venv-live`:
```powershell
py -3.12 -m venv .venv-live
.\.venv-live\Scripts\python.exe -m pip install -e ".[live]"
.\.venv-live\Scripts\python.exe -m buscainsta.live_probe --help
```

Defina as variáveis `BUSCAINSTA_IG_TEST_LOGIN` e `BUSCAINSTA_IG_TEST_PASSWORD` em ambiente local **sem publicar seu conteúdo**. Execute com `--input` (CSV de um voluntário autorizado), `--contact-id`, `--expected-username` e `--confirm-contact-sharing`.

O programa fará login com a conta de teste, enviará **um** `AddressBookContact`, tentará `address_book_unlink` e retornará apenas contagens, comparação booleana e estado de desconexão. Não há proxy, retry de challenges, extração em lote ou persistência de sessão. Se a desconexão falhar, revisar imediatamente a agenda da conta no Instagram.

**Interpretação:** `expected_username_in_suggestions=true` significa que a sugestão contém aquele perfil, mas não comprova que o telefone ou e-mail o causou (podem existir outros sinais). `schema_recognized=false` significa resposta não interpretada, **não** ausência de perfil. Um resultado negativo não prova que o cliente não tem Instagram. Nunca vincular contas ao CRM automaticamente.

Referência do método: https://subzeroid.github.io/instagrapi/3.0.18/usage-guide/user/
