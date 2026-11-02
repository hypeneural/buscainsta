# Radar de Concorrentes — arquivo local offline

## Estado da implementação
Esta branch implementa a **fundação offline e painel gerencial funcional**: cadastro individual ou em lote (com URLs do Instagram), ativação/pausa de perfis, importação de manifesto autorizado, SQLite isolado, mídia local deduplicada por SHA-256, snapshots de métricas, mural responsivo, timeline agrupada por dia, filtros avançados e testes HTTP. **Oferece leitura oficial Meta Business Discovery sob acionamento manual e com credenciais autorizadas**, mas não implementa login via Instagram privado, agendamento automático, download de Stories, download remoto de mídia, React/Masonic nem um Totem completo. Nada recupera Stories expirados, e nenhum arquivo pode ser garantido sem estar salvo antes de expirar.

A PR do painel de clientes é base da branch; não fazer merge isolado na main até integrar a dependência corretamente. Não acessar CRM ou conta do estúdio.

## Instalação Windows
Na branch desta PR, executar o setup Windows existente para criar .venv, depois:

```powershell
.\.venv\Scripts\python.exe -m buscainsta.radar.cli init
.\.venv\Scripts\python.exe -m buscainsta.radar.cli add-competitor amizphoto
.\.venv\Scripts\python.exe -m buscainsta.radar.cli import "C:\BuscaInstaRadar\manifest.json"
powershell -File scripts/start-radar-windows.ps1
```

Painel local: http://127.0.0.1:8766. O mural e a timeline são somente leitura; o cadastro/ativação de concorrentes permite POST JSON protegido por validação de origem e token CSRF. Não existe botão de coleta Instagram na UI: a leitura oficial de metadados é opcional e só ocorre mediante comando CLI explícito.

Por padrão os dados ficam em `%USERPROFILE%\BuscaInstaRadar`, separados do banco de clientes. Use `--root` para alterar o caminho em ambos os comandos. Nunca versionar a pasta privada.

## Como cadastrar e consultar os concorrentes

1. Abra o painel em `http://127.0.0.1:8766` e vá para **Visão geral**.
2. Digite `@perfil` ou o link `https://www.instagram.com/perfil/` e clique **Adicionar perfil**.
3. Para cadastrar os oito concorrentes fornecidos, clique **Adicionar os 8 concorrentes iniciais**. Alternativamente abra **Cadastrar vários concorrentes de uma vez**, cole um @ ou URL por linha (até 50) e confirme. Entradas repetidas não geram duplicatas.
4. Use **Pausar / Ativar** para desabilitar um monitoramento futuro sem remover seu histórico.
5. Em **Mural**, filtre por perfil, legenda, formato, período, presença de arquivo e ordenação.
6. Em **Timeline cronológica**, acompanhe publicações agrupadas por dia e hora local, sempre com as mais recentes primeiro.
7. O painel informa a data da última **importação ou consulta oficial sob demanda**; não apresenta esse horário como se todas as publicações do Instagram estivessem atualizadas. Não há agendador automático nesta fase.

O arquivo `config/radar_competitors.example.json` também traz os oito usernames. O cadastro por interface não exige linha de comando.

## API local

```text
GET  /api/config
GET  /api/stats
GET  /api/competitors
GET  /api/posts?username=&kind=&search=&from=&to=&sort=recent&archived=all&limit=40&offset=0
GET  /api/blob/{sha256}
POST /api/competitors           {username, name?}
POST /api/competitors/bulk      {usernames: ["@perfil", "https://www.instagram.com/outro/"]}
POST /api/competitors/status    {username, enabled: true|false}
```

`POST` exige `Origin` de mesma origem, `Content-Type: application/json` e `X-Radar-CSRF` obtido de `/api/config`. O token de CSRF não serve como autenticação remota; o acesso deve permanecer exclusivo à máquina local.

## Consulta opcional à Meta Graph API (Business Discovery)

Há um adaptador separado em `src/buscainsta/radar/meta_business.py` que utiliza **somente a API oficial Meta Graph**. Ele só funciona quando a conta dedicada é profissional, a integração tem as permissões necessárias e o perfil consultado é elegível (Business/Creator). Não promete acesso a contas pessoais, Stories, Insights privados, nem a dados ausentes/ocultos.

Configuração local (não registrar segredos no repositório):

```powershell
$env:RADAR_META_TOKEN = "<access_token_da_integracao_profissional>"
$env:RADAR_META_IG_USER_ID = "<ig_user_id_profissional_autorizado>"
$env:RADAR_META_VERSION = "v25.0"
.\.venv\Scripts\python.exe -m buscainsta.radar.cli sync-meta --username amizphoto --confirm-official-api
# Após verificar permissões de todos:
.\.venv\Scripts\python.exe -m buscainsta.radar.cli sync-meta --all --confirm-official-api
```

O token é transmitido em header Authorization via HTTPS e não deve ir para logs. O comando consulta no máximo 25 publicações recentes por perfil por padrão (parâmetro `--limit` de 1 até 30). A normalização inclui foto, vídeo, carrossel, legenda, horários, curtidas e comentários, quando disponíveis. Apenas referências aos arquivos são persistidas; **nenhum arquivo de foto ou vídeo é baixado automaticamente e o mural não carrega essas URLs de terceiros**. Portanto, a galeria visual completa exige mídia obtida e importada por um meio autorizado.

Erros de permissão ou indisponibilidade ficam registrados em `collection_runs` de modo sanitizado. A consulta é manual e não possui mecanismos de rotação de contas, evasão de bloqueio ou scraping de endpoints privados.

**Fonte oficial de referência:** https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/business_discovery

## Contrato do manifesto
Manifestos locais são um caminho explícito de importação, não um endpoint para buscar arquivos de terceiros. Apenas arquivos cujos direitos de obtenção e armazenamento foram verificados pelo operador.

```json
{
  "posts": [{
    "source":"manual",
    "external_id":"abc123",
    "username":"amizphoto",
    "kind":"carousel",
    "posted_at":"2026-11-01T15:00:00-03:00",
    "permalink":"https://www.instagram.com/p/abc123/",
    "caption":"Exemplo local",
    "likes":null,
    "comments":null,
    "assets":[
      {"kind":"image","file":"foto-autorizada.jpg"},
      {"kind":"video","file":"video-autorizado.mp4"}
    ]
  }]
}
```

`source`, `external_id`, `username`, `kind` e `posted_at` são obrigatórios. `kind` aceita image/video/carousel/story. Arquivos devem ficar no mesmo diretório do manifesto, ou usar `--media-directory`. Formatos de arquivo permitidos por assinatura: JPEG, PNG, WebP e MP4; limite 200 MiB por item.

`remote_url` é somente referência não arquivada; a interface **não a baixa nem a exibe**. Arquivos com mesmo SHA-256 são armazenados uma única vez; múltiplas publicações podem referenciar o mesmo conteúdo. Uma publicação repetida usa a chave canônica de permalink do Instagram, quando disponível, ou `source:external_id`. O mesmo par posição/publicação é atualizado em vez de duplicado. Cada alteração de métricas gera snapshot. A entrada idempotente preserva o primeiro horário de detecção.

## Contrato de segurança e escopo
- Sem login automatizado na API privada e sem scraping. Consultas externas só via comando explícito do adaptador oficial Meta; sem download de conteúdo de terceiros.
- Sem sincronização com CRM ou WhatsApp e sem Direct.
- Sessões e credenciais jamais dentro do GitHub; o Radar não requer nenhuma.
- Servidor somente em loopback. GET de leitura e POST estritamente restrito a cadastro/ativação de concorrentes, com validação Origin e token CSRF. Nunca expor a porta à rede pública.
- Validar autorização de captura e armazenamento antes de arquivar material de terceiros. Mesmo perfis públicos não concedem automaticamente direitos de cópia.
- Não supor que ausência de coleta significa ausência de Story.
- Backup: copiar `radar.db` com procedimento consistente de SQLite e o diretório `blobs/` juntos. Não executar backup copiando apenas o .db enquanto WAL estiver ativo.
- Não deletar blobs automaticamente; introduzir política de retenção e limpeza de órfãos após revisão.
- A timeline aplica sempre a ordem **mais recentes primeiro**, pelo horário original da publicação no fuso America/Sao_Paulo. O mural permite ordenar por hora, curtidas, comentários e detecção recente; as métricas ausentes aparecem como indisponíveis, não zero.
- O filtro de arquivos locais ajuda a distinguir publicações que possuem arquivo preservado das que têm apenas metadados. Baixar uma mídia não faz parte da interface.
- Deduplicação: chave canônica do permalink quando disponível; tabela adicional `post_identities` une reimportações da mesma origem mesmo se a próxima consulta não trouxer permalink. O arquivo usa SHA-256; múltiplos posts podem referenciar o mesmo blob.
- Vídeos locais suportam HTTP byte ranges (206), permitindo carregamento parcial e navegação.
- Próximas fases: paginação completa e agendamento autorizados da Graph API, gerenciamento de direitos, cache/asset worker, React Masonic + lightbox, monitoramento de integridade, backup e testes E2E reais no Windows.

## Referências
- instagrapi (experimental, não oficial): https://github.com/subzeroid/instagrapi
- Masonic: https://github.com/jaredLunde/masonic
- Yet Another React Lightbox: https://github.com/igordanchenko/yet-another-react-lightbox
- Meta Instagram API: https://developers.facebook.com/docs/instagram-platform/
