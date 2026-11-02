# BuscaInsta — Painel local Windows 11

Painel em http://127.0.0.1:8765/ que lê CSV de clientes do BuscaInsta e, opcionalmente, um CSV de resultados do live_sync. Registra tudo em SQLite privado, fora do Git.

## Campos e ações
- Editar @: altera candidato e remove confirmação anterior/permissionamento do Direct.
- Consultar foto/seguidores: pesquisa individual por @; devolve relação por conta autenticada em 3 estados (Sim, Não, Desconhecido) e salva miniatura em pasta privada.
- É o cliente: confirmação MANUAL pelo operador, não pelo titular; não é automática.
- Permissão Direct: check individual do operador para contatos elegíveis/autorizados.
- Enviar Direct: prévia da mensagem fixa, clique individual, bloqueio contra reenvio automático. Registra horário UTC da tentativa e horário do aceite da API; aceite não prova entrega ou leitura.

## Primeira execução, sem acesso ao Instagram
Na branch da PR #1 atualizada, rode:

    .\.venv\Scripts\python.exe -m pytest -q tests/test_dashboard.py tests/test_live_sync.py
    .\.venv\Scripts\python.exe -m pytest -q
    .\.venv\Scripts\python.exe -m buscainsta.dashboard --db "C:\BuscaInstaPrivado\buscainsta.db" --contacts "C:\BuscaInstaPrivado\contatos.csv" --account "estudio_teste"

O argumento opcional --review recebe o CSV criado pelo live_sync. A importação local aceita até 10.000 linhas do CSV com 8 colunas do BuscaInsta, inclusive contatos cujo consentimento para marketing ainda está pendente. A importação não dispara mensagens.

## Ativar consultas individuais ao Instagram
Login do Chrome não é reaproveitado. Biblioteca não oficial, requer credenciais da conta de teste via variáveis BUSCAINSTA_IG_TEST_LOGIN e BUSCAINSTA_IG_TEST_PASSWORD; instalação separada:

    py -3.12 -m venv .venv-live
    .\.venv-live\Scripts\python.exe -m pip install -e ".[live]"
    .\.venv-live\Scripts\python.exe -m buscainsta.dashboard --db "C:\BuscaInstaPrivado\buscainsta.db" --account "estudio_teste" --enable-instagram

Somente o clique Consultar faz chamada à instagrapi. Falha de imagem não bloqueia a consulta de seguidores. Falha na consulta não é interpretada como Não.

## Ativar Direct individual
Após conferir elegibilidade e autorização para a mensagem, crie o arquivo privado C:\BuscaInstaPrivado\mensagem-direct.txt (UTF-8) com o texto fixo:

    .\.venv-live\Scripts\python.exe -m buscainsta.dashboard --db "C:\BuscaInstaPrivado\buscainsta.db" --account "estudio_teste" --enable-instagram --enable-dm --message-file "C:\BuscaInstaPrivado\mensagem-direct.txt"

O botão requer confirmação manual do perfil, permissão Direct e consulta recente na MESMA conta. Após uma tentativa, mesmo que o resultado seja desconhecido, não há reenvio automático. Um aceite devolvido pela biblioteca não comprova a entrega. Evitar campanhas frias/automatizadas; conferir termos e política Meta.

## Segurança e privacidade
- Servidor escuta exclusivamente em 127.0.0.1; Host, Origin e token CSRF para escrita; sem CORS remoto.
- Arquivos pessoais, SQLite, miniaturas, sessões e senhas jamais podem ser enviados ao GitHub.
- A foto tem filtro por domínio HTTPS de CDN, tipo, assinatura e tamanho. URLs CDN podem expirar.
- Quatro contas Instagram: usar **um SQLite separado por conta** até migração para modelo multi-conta; relações são dependentes de cada conta.
- CI usa apenas FakeClient e nunca conecta ao Instagram ou envia Direct real.
- O usuário confirma manualmente o perfil; uma sugestão baseada em nome não confirma identidade.

## Aceite
CI novo 4/4; Windows local; painel com tabela/foto, busca e paginação; followers nos dois sentidos por conta; confirmação e Direct permission; teste de envio com FakeClient e timestamp; checagem de pastas privadas e ausência de dados pessoais no repo.
## Atalho PowerShell

O script `scripts/start-dashboard-windows.ps1` lê o venv já instalado e inicia a tabela. Exemplo sem rede:

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dashboard-windows.ps1 -Db "C:\BuscaInstaPrivado\buscainsta.db" -Contacts "C:\BuscaInstaPrivado\contatos.csv" -Account "conta_teste"

Para consulta individual adicionar `-EnableInstagram` e informar `-Account` com o **username efetivamente autenticado**, sem @. Para Direct, adicionar `-EnableDirect -MessageFile "C:\BuscaInstaPrivado\mensagem-direct.txt"` e obter autorização individual antes do clique. O adaptador bloqueia quando o usuário autenticado não corresponde a `-Account`.

## Aproveitar o painel_conferencia.html existente — MIGRAÇÃO RECOMENDADA

Foi identificada uma cópia do painel local com **2.739 linhas e 289 perfis candidatos**, ranking VIP P0–P4, busca, filtros e 562 IDs de CRM repetidos entre as linhas. Isso NÃO significa 562 registros duplicados: os telefones desta versão são distintos. Por isso a migração utiliza **telefone normalizado como chave de junção**, mantendo o ID do CRM apenas como atributo, sem associar erroneamente pessoas diferentes.

**Não alterar, renomear, sobrescrever ou publicar o HTML original**. O novo painel lê a matriz `const allData = [...] ` via decoder JSON, sem executar JS, e faz a migração para SQLite privado. O HTML anterior permanece como backup visual.

No Windows 11, primeiro execute sem conexão Instagram:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dashboard-windows.ps1 `
  -Db "C:\BuscaInstaPrivado\buscainsta.db" `
  -LegacyPanel "C:\BuscaInstaPrivado\painel_conferencia.html" `
  -Account "estudio_teste"
~~~

Abra **http://127.0.0.1:8765/** (não `file://`) para utilizar os botões e a persistência. Um backup consistente do SQLite existente é gerado em `buscainsta.db.before-legacy.backup` na primeira migração. Se houver banco em uso, interrompa antes a instância anterior do painel.

A tela conserva **ranking VIP, score, segmentos, indicadores, consulta por nome/telefone/@/ID, ensaios históricos, LTV e situação de Natal 2026**. Também acrescenta foto, seguidores nos dois sentidos por conta, checkbox de conferência do gestor, permissão de Direct, texto fixo e horário da tentativa/aceite.

**Verificação obrigatória da migração:** total de 2.739 linhas, 289 candidatos Instagram, P0=232, P1=56 e P2=654. Se o HTML local tiver sido atualizado, documentar a diferença, **não forçar números antigos**. Reexecutar o import deve atualizar contexto histórico sem apagar confirmações já registradas e sem duplicar linhas. O CSV ainda pode ser importado separadamente quando necessário.

**Nota de segurança:** o HTML original inclui dados pessoais embutidos em JavaScript e renderiza parte da tabela com `innerHTML`. O novo painel usa dados via API local e cria células com `textContent`, evitando interpretar nomes de clientes como HTML. Não publicar screenshot real/HTML/SQLite em issue ou PR.
