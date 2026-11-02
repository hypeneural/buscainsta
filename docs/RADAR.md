# Radar de Concorrentes — arquivo local offline

## Estado da implementação
Esta branch implementa a **fundação offline funcional**: cadastro de concorrentes, importação de manifesto autorizado, SQLite isolado, mídia local deduplicada por SHA-256, snapshots de métricas, visualizador web e testes. **Não implementa login Instagram, coleta automática, download de Stories, download remoto, React/Masonic nem agendador**. Nada recupera Stories expirados, e nenhum arquivo pode ser garantido sem estar salvo antes de expirar.

A PR do painel de clientes é base da branch; não fazer merge isolado na main até integrar a dependência corretamente. Não acessar CRM ou conta do estúdio.

## Instalação Windows
Na branch desta PR, executar o setup Windows existente para criar .venv, depois:

```powershell
.\.venv\Scripts\python.exe -m buscainsta.radar.cli init
.\.venv\Scripts\python.exe -m buscainsta.radar.cli add-competitor amizphoto
.\.venv\Scripts\python.exe -m buscainsta.radar.cli import "C:\BuscaInstaRadar\manifest.json"
powershell -File scripts/start-radar-windows.ps1
```

Painel somente leitura: http://127.0.0.1:8766.

Por padrão os dados ficam em `%USERPROFILE%\BuscaInstaRadar`, separados do banco de clientes. Use `--root` para alterar o caminho em ambos os comandos. Nunca versionar a pasta privada.

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
- Sem login automático, sem API privada, sem scraping, sem download de terceiros.
- Sem sincronização com CRM ou WhatsApp e sem Direct.
- Sessões e credenciais jamais dentro do GitHub; o Radar não requer nenhuma.
- Servidor somente em loopback e GET de leitura; POST rejeitado.
- Validar autorização de captura e armazenamento antes de arquivar material de terceiros. Mesmo perfis públicos não concedem automaticamente direitos de cópia.
- Não supor que ausência de coleta significa ausência de Story.
- Backup: copiar `radar.db` com procedimento consistente de SQLite e o diretório `blobs/` juntos. Não executar backup copiando apenas o .db enquanto WAL estiver ativo.
- Não deletar blobs automaticamente; introduzir política de retenção e limpeza de órfãos após revisão.
- Próximas fases: coletor oficial separado, gerenciamento de direitos, cache/asset worker, React Masonic + lightbox, monitoramento de integridade, deduplicação por ID estável, índices e testes E2E no Windows.

## Referências
- instagrapi (experimental, não oficial): https://github.com/subzeroid/instagrapi
- Masonic: https://github.com/jaredLunde/masonic
- Yet Another React Lightbox: https://github.com/igordanchenko/yet-another-react-lightbox
- Meta Instagram API: https://developers.facebook.com/docs/instagram-platform/
