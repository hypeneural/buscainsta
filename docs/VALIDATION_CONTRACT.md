# Contrato de validação e matriz forense (P0 offline)

Atualizado em 31/10/2026, após a homologação local (Windows 11 Pro/Python 3.12.10) informada pelo operador.

## Natureza desta fase
**Não existe descoberta de Instagram por telefone ou e-mail.** O módulo valida a sintaxe e a forma de dados CSV locais, não garante propriedade de e-mail/número, existência de conta, consentimento jurídico, identidade do titular ou match `@username`.

`network_calls: 0` e `external_uploads: 0` são estados declarativos do app (não há integrações implementadas), **não medições de tráfego**. A instalação do Python/pip pode fazer conexões para obter dependências.

## Dois modos de execução distintos

### Teste totalmente sintético — `--synthetic`
- Até 100 registros gerados localmente por `sample`, com ID `TEST-001` ... `TEST-100`.
- `full_name` exatamente `Pessoa Ficticia 001` etc.
- E-mail exatamente `test001@example.invalid` etc. `example.invalid` é domínio reservado e não entrega mensagens.
- **Telefone vazio**. Nunca gerar telefones que pareçam discáveis.
- `instagram` e `consent_date` vazios.
- `consent=test_only` e `consent_source=synthetic`.
- Alterar qualquer identificador ou injetar número/usuário real deve invalidar a linha.
- Não use o sinalizador `--synthetic` em dados originados do CRM.

### Dados locais com consentimento específico — `--local-consented`
- O operador precisa selecionar **expressamente** esse modo; ele nunca é o padrão.
- Campos: `contact_id,full_name,phone,email,instagram,consent,consent_date,consent_source`.
- `consent=yes` com data ISO `AAAA-MM-DD` válida e fonte não vazia são **marcadores de contrato**, não prova legal de aceite.
- Os arquivos reais devem ficar fora do repositório público; nenhum dado pessoal deve ser incluído em teste automatizado, PR, log ou comentário.
- Nenhum dado é enviado para Meta ou CRM. Os valores do arquivo não aparecem no resumo JSON; dados ainda existem no disco do usuário e exigem tratamento adequado.
- Não execute esse modo em dados reais sem comprovação de autorização específica e avaliação de privacidade.

## Validação de arquivos e campos

| Categoria | Regra | Limitação |
| --- | --- | --- |
| CSV | UTF-8 (BOM aceito), cabeçalho exato, sem duplicata, linha completa | Não cobre todos os formatos exportados pelo CRM |
| Tamanho | Até 100 linhas, 1 MB, 512 caracteres por campo | Não é processamento em lote |
| IDs | Obrigatórios e únicos | Não valida IDs contra o CRM |
| E-mail | Sintaxe comum ASCII, domínio com labels válidas | Não consulta DNS, MX nem comprova titularidade |
| Telefone | DDD brasileiro reconhecido; móvel com 11 dígitos/9 e fixo com 10/2–5 | Não consulta operadora nem garante número ativo; casos especiais não são suportados |
| Consentimento | Data válida não futura e fonte presente | Não comprova base legal |
| Instagram | Não busca nem confirma contas | Em modo sintético deve estar vazio |
| Privacidade | Relatório de contagens agregadas | Não é monitor de rede nem DLP completo |

## Critérios de aceite do Antigravity

1. Executar setup duas vezes (primeira com pip; segunda com `-SkipInstall`) e verifier isolado.
2. `pytest -q` passa no Windows 11/Python 3.12 e CI Windows+Ubuntu (3.11/3.12).
3. `sample` gera 100 linhas sem números de telefone e com domínio `example.invalid`.
4. `validate --synthetic` retorna 100/100; qualquer número inserido, username ou nome trocado invalida a linha.
5. `validate` sem modo falha com exit 2; `--local-consented` é opção explícita.
6. Registros com DDD inválido, Unicode no telefone, e-mail com hostname inválido, consentimento ausente e CSV quebrado devem ser rejeitados e não revelar conteúdo pessoal no relatório.
7. `git diff --check`, `git status`, `git ls-files` e CI na SHA final sem PII.
8. A PR deve permanecer Draft até revisão e aprovação separadas, sem merge automático.

## Etapa posterior e separada
Captura voluntária de `@Instagram` pelo próprio cliente ou integração oficial baseada em interações iniciadas pelo titular. Nenhuma busca por telefone/e-mail via API privada do Instagram nesta fase.
