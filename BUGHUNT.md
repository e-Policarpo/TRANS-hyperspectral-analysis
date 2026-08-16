# Bughunt TRANS

Lista corrente de bugs e melhorias encontradas no uso real do TRANS.
Cada item começa não-resolvido (`- [ ]`); marque `- [x]` quando o fix
estiver no `Unified-UI` (e cole o hash do commit ao lado).

Última atualização: 2026-06-03.

---

## WITec Loader

- [ ] **Metadados da lente errados.** O nome dos arquivos herdou a
  mesma lente para todos os espectros. O certo seria conferir
  arquivo por arquivo — provavelmente o campo está sendo lido uma
  única vez do projeto raiz em vez de por TDText/InfoBlock de cada
  espectro.
- [ ] **Agrupamento incorreto de espectros.** Atualmente o loader
  junta num único dataset todos os espectros que compartilham o
  mesmo range em X. Cada espectro deveria virar um dataset
  separado (ou ao menos manter a identidade individual no
  dataframe — coluna por espectro, não merge por X).

## Sistema de gráficos e tabelas

- [x] **Downsampling em gráficos densos.** Para que a UI não trave
  com curvas de >100k pontos.
  *Verificado ATIVO: o render nativo chama `prepare_curve_xy(...,
  max_points=_MAX_PATH_POINTS, downsample_mode=DOWNSAMPLE_PEAK)` com
  `_MAX_PATH_POINTS=50_000`. Teste headless: curva de 1.000.000 pts →
  100.000 elementos no path (50k blocos peak × 2 = min/max por bloco,
  preserva o envelope). O caminho matplotlib (fallback) também reduz
  via `step = len // max(2000, w*2)`. (A nota antiga dizia 100k; hoje
  são 50k blocos.)*
- [ ] **Réguas/ticks do gráfico dessincronizando com os dados.**
  Reportado 2026-06-29: os ticks dos eixos não casariam com a
  curva ("sempre, ao abrir"). NÃO REPRODUZIDO até agora: render
  headless (nativo *e* fallback matplotlib) com dados realistas
  (I(V) Omicron, y~1e-9, NaN nas pontas) mostra alinhamento
  pixel-perfeito (tick x=0 e curva V=0 ambos em px 420.0;
  `_native_data_x_to_pixel` == `_native_build_transform`, Δ=0 em
  zoom/resize/log). FALTA: screenshot do estado quebrado +
  confirmar `TRANS_FAST_RENDER` e se é HiDPI/Retina ou um dataset
  específico. Ver `qml_graph_canvas.py` (`_renderNative` /
  `_native_draw_axes`).
- [ ] **Culling de dados fora da viewport.** Não desenhar segmentos
  que estão fora do `ax_rect`.
  *Status: clipping em nível de pixel JÁ ativo — `_renderNative` faz
  `painter.setClipRect(ax_rect)`, então segmentos fora do eixo não são
  rasterizados. NÃO há culling em nível de dados (descartar pontos fora
  do x-range antes de montar o path) — e isso é proposital: o
  `QPainterPath` é cacheado em coords de DADOS e reusado em zoom/pan
  sem rebuild; cull por view-range forçaria rebuild a cada zoom/pan e
  mataria o cache. Com o cap de 50k pts o custo de traversal já é
  limitado. Recomendação: deixar como está.*
- [ ] **Area select para zoom mapeia coordenadas erradas.** O zoom
  resultante sai deslocado em relação ao retângulo selecionado.
  *Investigação: no render nativo (default) o round-trip é
  PIXEL-EXATO — provado por teste headless (`ViewBoxState` +
  `_native_build_transform`, offset 0.0) e travado em regressão
  (`test_area_select_zoom_is_pixel_exact`). Não consegui reproduzir
  deslocamento no caminho nativo. PORÉM achei e corrigi um bug REAL de
  coordenadas vizinho — ver abaixo. Se o deslocamento persistir p/ a
  usuária, é específico de ambiente (device-pixel-ratio/Retina) e
  preciso de um print/repro p/ atacar.*
- [x] **Clique em curva não seleciona (modo nativo).** `_findNearestCurve`
  media o clique com o transform NATIVO (`_dataToPixel`) mas os pontos
  da curva com `self.axes.transData` (matplotlib) — que no modo nativo
  nunca é layoutado (limites 0–1 default), então o clique nunca casava:
  selecionar curva clicando ficava quebrado. *Fix: mapeia ambos via
  `_dataToPixel` (um só espaço de coords; cobre nativo + fallback +
  log). Testes `test_find_nearest_curve_hits/misses_in_native_mode`.*
- [x] **Panning.** Adicionar pan dedicado nos gráficos.
  *Nota: o ViewBox da Phase 2 já tem `MOUSE_MODE_PAN`; verificar
  se a toolbar do `GraphWindowContent.qml` está expondo o toggle
  corretamente.*
  *Fix: a toolbar já expunha o toggle corretamente
  (`graphCanvas.mouseMode = checked ? "rect" : "pan"`), mas
  `ViewBoxState.handle_press_left` ignorava o modo e sempre
  iniciava zoom-rect. Agora, em modo pan, o left-drag faz pan
  (`viewbox.py`); right-drag continua sempre fazendo pan. Testes
  em test_viewbox.py atualizados + novo `test_left_drag_pans_in_pan_mode`.*
- [x] **Tabela ↔ spectral data.** Adicionar funcionalidade de
  converter uma tabela em spectral data (ou unificar os dois no
  backend mantendo separação organizacional no project browser).
  *Fix (Phase A, `f6ccf27`): promoção one-way tabela→dataset.
  `TableDataModel.to_dataframe()` + `canBeDataset()`;
  `AppBackend.createDatasetFromTable()` coage p/ numérico, constrói
  `SpectralData`, registra em `_datasets`, emite `dataLoaded`, é
  undoable. Botão "Add as Dataset" em `TableWindowContent.qml`.
  10 testes em test_table_to_dataset.py.*
- [x] **Operações sobre gráficos não disparam.** Smoothing (e
  provavelmente outros botões) emite o log
  `Opened dataset … - Smoothed in embedded windows` mas o gráfico
  não é alterado. O backend processa, mas o resultado não chega
  ao canvas.
  *Investigação: há DOIS caminhos. (a) Botões da toolbar do
  gráfico (`GraphWindowContent.qml` → `graphCanvas.applyCurveOperation`)
  adicionam uma nova curva ao canvas e funcionam. (b) Ferramentas
  a nível de dataset criam um dataset derivado (`X - Smoothed`,
  metadata `original=X`) que só aparecia no browser; ao abrir
  emitia `openDatasetEmbedded` → JANELA NOVA em vez de tocar o
  canvas aberto.*
  *Fix (decisão do usuário: OVERLAY na janela da fonte). Identidade
  janela↔dataset: o WindowManager guarda `datasetName` por janela
  (`findGraphWindowByDataset`, `addCurvesToGraphWindow`). No backend,
  `_on_tool_completed` chama `_route_derived_datasets()` que DIFFA
  `_datasets` contra `_seen_dataset_keys` (cobre TODA ferramenta
  espectral que carimba `original` — smoothing, baseline, cosmic-ray,
  derivada, bg-sub, bandgap/doping, …; ignora map-gen e imports) e
  emite `displayDerivedDataset(source, result, curves, …)`. QML
  (`onDisplayDerivedDataset`) acha a janela da fonte e SOBREPÕE a
  curva (raise; sem 2ª janela); se a fonte não está aberta, abre
  janela nova p/ o resultado. `_workflow_mode` suprime (resultados
  intermediários não viram janela). Seed de `_seen_dataset_keys` no
  load de projeto p/ não floodar no 1º tool. 5 testes em
  test_derived_dataset_routing.py.*
- [x] **Toggle zoom/pan não funciona.** Pan continua em botão
  direito e zoom em botão esquerdo independentemente da seleção
  na toolbar; ambos mapeiam coordenadas erradas.
  *Fix (parte do toggle): `handle_press_left` agora respeita
  `mouseMode` — modo "pan" faz pan no botão esquerdo, modo "rect"
  faz zoom-rect. Ver fix de Panning acima. NOTA: a parte
  "mapeiam coordenadas erradas" (deslocamento do retângulo, item
  separado abaixo) não foi investigada nesta sessão — o
  round-trip `_dataToPixel`/`_pixelToData` parece consistente;
  suspeitar de device-pixel-ratio (Retina) se persistir.*
- [x] **Posição inicial dos gráficos.** Deveria auto-centralizar /
  auto-fit os dados (todos os pontos visíveis) ao abrir uma nova
  janela.
  *Fix: `resetView()` agora enquadra os dados DIRETO das curvas
  (`_calculateAutoBounds`), sem depender da extensão registrada num
  paint anterior — então funciona antes do 1º render. O
  `GraphWindowContent.qml` chama `graphCanvas.resetView()` logo após
  carregar as curvas (em `onCurvesChanged` e `Component.onCompleted`),
  garantindo o auto-fit ao abrir. Bônus: `_calculateAutoBounds` foi
  reescrito p/ setar o range em UM `set_view_range` (antes ia por 4
  setters que faziam `sorted()` contra o range default 0–1 →
  inflava a margem do 1º frame); agora a margem de 5% é exata já na
  1ª chamada. Testes: `test_reset_view_frames_data_before_any_paint`,
  `test_auto_bounds_exact_margin_is_stable_first_call`,
  degenerate/empty + no-curves.*

## Sistema de Widgets

- [x] **Zona de captura do mouse na janela inteira.** Hoje só a
  barra superior reage ao foco; o mouse dentro do conteúdo da
  janela não direciona os comandos para essa janela específica.
  *Causa: havia um MouseArea "click anywhere to bring to front"
  em `EmbeddedWindow.qml`, mas com `z: -1` (atrás do conteúdo). No
  Qt Quick o press vai pro item de cima primeiro; o conteúdo
  (canvas/botões) consome o press e ele nunca cai pro MouseArea
  atrás. Pôr na frente roubaria todos os cliques do conteúdo.
  Fix: trocado por um `TapHandler` (passive grab) que vê o press
  em qualquer lugar — inclusive sobre conteúdo interativo — sem
  roubá-lo; `gesturePolicy: DragThreshold` cede em drag (pan/zoom
  do canvas seguem funcionando).*
- [ ] **Ctrl+C / Ctrl+V** (mensagem cortada — copiar para tabelas?
  para gráficos? Confirmar escopo).

## Sistema de Imagens

- [x] **Sensibilidade do scroll de zoom muito alta.** Diminuir o
  passo por wheel-tick.
  *Fix: `wheelEvent` aplicava `1.1×` fixo POR EVENTO; em trackpad
  macOS chegam muitos eventos sub-notch → zoom dispara. Agora o
  fator é proporcional ao delta: `1.1 ** (delta/120)` (uma notch
  de mouse = 120 = um passo 1.1×). Lógica extraída p/
  `_zoom_by_delta` (testável). Ver `qml_image_canvas.py`.*
- [x] **Limite de zoom-out.** Não permitir reduzir abaixo do
  tamanho original da imagem.
  *Fix: piso de zoom era 0.05 (encolhia muito). Agora o piso é
  `min(fit_scale, 1.0)` — não dá p/ reduzir abaixo do tamanho
  ajustado à janela (ou 1:1 p/ imagens menores que a janela). Ao
  sair do fit-to-window, `_zoom` é semeado com `fit_scale` p/
  evitar salto no primeiro passo. Testes em
  test_qml_image_canvas.py.*
- [ ] **Overlays de espectros duplicados.** Espectros estão sendo
  desenhados mais de uma vez no overlay; causa raiz não-óbvia.
  *Investigação: com `showLaserFocus`/`showCrosshair` off (default),
  só o Repeater `selectedOverlays()` desenha — uma "+" por
  spectrum. Duplicação ⇒ `getDatasetOverlaysForImage` retorna o
  mesmo spectrum físico sob dois `dataset_name` (datasets que
  compartilham `wip_source_stem` + mesma posição). Causa raiz é o
  merge/identidade do WITec loader (bug #2 da seção WITec) — o fix
  pertence ao loader, não ao overlay. Dedupe no overlay mascararia
  o bug real.*
- [x] **Legenda fantasma no overlay.** Quando o usuário
  desseleciona um espectro na lista, a entrada correspondente
  fica na legenda.
  *Fix: a legenda iterava `overlayPool` (todos) e só esmaecia os
  desmarcados (opacity 0.35). Agora usa `selectedOverlays()`, em
  lock-step com a crosshair na imagem. `ImageWindowContent.qml`.*
- [ ] **"WITec probe offset" aparece p/ imagens não-WITec.** O
  visualizador de imagens (`ImageWindowContent.qml`) mostra a seção
  "WITec probe offset" (ΔX/ΔY, "Show video centre") mesmo para
  imagens Omicron MATRIX (ex.: scan `…112539 5_1 I`), onde não se
  aplica. O probe offset (laser − centro do vídeo) só faz sentido
  p/ dados WITec. FALTA: condicionar a seção à fonte WITec
  (ex.: `image.metadata.source` / `additional_info`) — esconder p/
  Omicron e demais. Reportado 2026-06-29; ver para depois.

- [x] **Mapas sem espectros associados ficam brancos ao ativar
  grid overlay.** Provavelmente um divide-by-zero ou um
  `imshow` com array vazio quando o map data ainda não tem
  espectros vinculados.
  *Fix: confirmado divide-by-NaN. Map sem espectros vinculados é
  all-NaN; `np.nanpercentile` retorna NaN → níveis (lo,hi)=NaN →
  LUT faz `(data-NaN)/NaN` → tudo NaN → branco. O guard `hi<=lo`
  não pegava (comparação com NaN é False). Extraído
  `_compute_display_levels()` que trata all-NaN/vazio/constante e
  garante lo/hi finitos com hi>lo (fallback 0..1). `getValueRange`
  também usa o helper. Testes em test_qml_map_canvas.py.*
- [ ] **Overlays não aparecem nesta aba.** Os overlays de
  espectros (que funcionam no modo Spectral) não são herdados
  pela aba hiperespectral. Average spectrum também não puxa os
  gráficos.
- [ ] **Grid 1x1 aplica tamanho errado.** Quando o usuário coloca
  grid 1×1 explicitamente, o código aplica outro tamanho.
- [x] **Average spectrum lê número errado de blocos.** Adicionar
  limpeza de cache ao trocar o tamanho do grid e reprocessar a
  média.
  *Investigação: a seleção JÁ é limpa ao trocar o grid
  (`setGridBlockSize` faz `_selected_blocks.clear()`). O bug real
  era inconsistência de guard: o canvas decide bloco-vs-pixel com
  `block_h > 1 OR block_v > 1`, mas o backend
  (`getAverageSpectrumForSelectedBlocks` e `invertSelection`) só
  checava `block_h > 1`. Num grid 1×N (blocos altos) o canvas
  guarda coords de bloco, mas o backend as lia como pixel →
  média de 1 spectrum em vez de N (block_count errado). Guards
  alinhados. Teste de regressão em test_hyperspectral_workflow.py.*
- [x] **Suporte a espectros espacialmente resolvidos não-mapas.**
  Espectros pontuais e em linha (line scans) precisam ser
  reconhecidos além de mapas em área.
  *Fix: como os loaders só guardam `Point_N` (sem coords x,y reais),
  line scans e point sets viram uma sequência ordenada 1×N (eixo
  espacial = índice do ponto). (1) Reconhecimento:
  `AppBackend.spatialLayout(name) -> area/line/point/none` +
  `spatial_layout` em `getDatasetListWithInfo`. (2) Entrada: ação
  "Open in Hyperspectral" no menu de contexto do ProjectBrowser
  (só p/ datasets line/point) → sinal `openInHyperspectralRequested`
  → Main.qml troca p/ aba 1 e chama `loadDatasetAsLineScan`. (3)
  Visualização (toggle no status bar): `map_editor_backend`
  `loadDatasetAsLineScan(name, view)` constrói **kymograph** (P×N =
  `spectra.values`, coluna j = espectro j) ou **strip** (1×N = média
  por coluna) e entra em line-scan mode (reseta o MultiChannelMap
  pois as shapes diferem). (4) Inspeção: `getSpectrumFromDataset`
  resolve por COLUNA em line-scan mode (clica qualquer linha → espectro
  da posição). Sai do modo ao carregar um mapa de área. 14 testes em
  test_line_scan_support.py.*
  *Follow-ups (fora do escopo): média sobre posições selecionadas +
  semântica do line-profile no modo line-scan; eixo-Y do kymograph
  rotulado com a variável independente real (canvas desenha índices);
  overlays nesta aba (item separado); abrir o cubo de um dataset de
  área direto.*
- [ ] **Zoom não funciona** nesta aba.
- [x] **Crosshair invisível.** Selecionando a ferramenta
  crosshair, o cursor desaparece dentro do canvas.
  *Fix: a ferramenta CROSSHAIR seta `Qt.BlankCursor` (esconde o
  cursor do OS) p/ desenhar uma cruz custom no lugar. `hoverMoveEvent`
  já atualizava `_crosshair_pos`, MAS o desenho exigia também
  `_show_crosshair` (flag separada que a ferramenta nunca liga) →
  cursor sumia sem substituto. Agora desenha quando
  `_current_tool == CROSSHAIR` também. `qml_map_canvas.py`.*
- [ ] **Line profile.** Não lê a distância correta no eixo X e
  aceita perfis que saem da área da imagem.
- [x] **NoneType ao abrir gráfico sem ponto associado.**
  ```
  An error occurred executing the property metacall WriteProperty
  on property "selectedCurveId" of QMLGraphCanvas(0x…)
  TypeError: 'NoneType' object is not callable
  ```
  *Fix: `selectedCurveId` no `QMLGraphCanvas` era `@Property(int)`
  só-leitura (sem setter, sem notify). O handler `onCurveSelected`
  em `GraphWindowContent.qml` fazia `selectedCurveId = curveId` —
  nome não-qualificado que resolvia p/ a property só-leitura do
  canvas → metacall WriteProperty chamava setter inexistente
  (None). Agora é Property read/write com notify
  (`selectedCurveIdChanged`); o write não quebra e os bindings
  `enabled: canvas.selectedCurveId >= 0` da toolbar ficam reativos
  (antes nunca atualizavam). Removido o `property selectedCurveId`
  local morto e o write redundante. Testes em
  test_qml_graph_canvas.py (novo).*

## Interface Hiperespectral (touch-up) — reportado 2026-07-01

- [x] **Line profile "gruda" em pixel absoluto ao redimensionar.** Ao
  desenhar um line profile no mapa, a linha desenhada se desloca
  quando a janela muda de tamanho (windowed ↔ fullscreen): a linha
  parece fixa numa posição de pixel ABSOLUTA da tela, não nas
  coordenadas de dados do canvas. Provável: o overlay do line
  profile (`qml_map_canvas` `_profile_line` / `MapTool.LINE_PROFILE`)
  guarda/desenha em px de tela em vez de (row,col) de dados, então
  dessincroniza no resize. Converter start/end p/ coords de dados e
  redesenhar via `_dataToPixel`.
  *FIX: `_profile_line` agora guarda frações-de-axes*
  *(`_pixel_to_axesfrac`/`_axesfrac_to_pixel`), redesenha contra o
  axes rect atual; `profileDrawn` emite coords de dados via
  `_pixelToData` (também corrigiu a margem de axes ignorada no QML).*
- [x] **Dots: média no painel + índice no hover + só no POINTER.**
  (a) Ao clicar nos dots p/ plotar, a média (mixed) dos dots
  selecionados deve aparecer TAMBÉM na caixa "Average Spectrum" do
  próprio analisador hiperespectral (hoje só diz "Select blocks on
  map to see average spectrum"). (b) Além do highlight atual, mostrar
  o NÚMERO/índice do dot num popup ao passar o mouse (hover), p/ o
  usuário saber qual dot vai clicar. (c) Os dots só devem ser
  interativos quando a ferramenta POINTER está ativa — ao desenhar
  linhas (ou outra tool) o hit-test dos dots NÃO deve interferir
  (hoje `mousePressEvent` intercepta em qualquer tool).
  *FIX: (a) sinal `stsAverageUpdated`→`InlineSpectrumViewer.*
  *showStsAverage` (média NaN-aware dos dots selecionados). (b) chip*
  *"#idx" no hover (`_hover_sts`). (c) click+hover gated a*
  *`MapTool.POINTER` via `_sts_marker_at`.*
- [x] **Masks não faz nada → remover/comentar por ora.** Comentar no
  código a seção Masks (não funciona atualmente).
  *FIX: GroupBox Masks comentado (`/* */`) em `DataBrowser.qml`.*
- [x] **Channel statistics e value readout mostram só zero.** O
  readout de valor no point inspector ("(215,632) = −0.0000") e as
  estatísticas de canal / do line profile ("Min/Max/Mean: −0.000")
  mostram 0 p/ correntes STM pequenas (~1e-7 A). O plot do line
  profile mostra os valores certos (~-4.6e-7), então é FORMATAÇÃO:
  usar notação científica / mais algarismos significativos nesses
  readouts (não `%.3f`).
  *FIX: novo `Fmt.js` (`sci(v,sig)`, notação científica p/ |v|<1e-3*
  *ou ≥1e5) usado em Statistics/Profile/PointInspector/coordLabel.*
  *Campos editáveis vmin/vmax mantidos com `.toFixed`.*
- [x] **Redesenho do painel direito.** O painel inteiro do lado
  direito deve ser UMA caixa rolável (como a seção de discretização
  já é). Os separadores entre seções devem ser arrastáveis p/
  redimensionar/esconder cada seção, e ter um botão p/ colapsar a
  seção quando não usada (além do scroll). Metadata de mapas deve
  mostrar info sobre os espectros associados.
  *FIX: novo `CollapsibleSection.qml` (header=separador c/ chevron*
  *▼/▶ p/ colapsar + handle inferior p/ arrastar-redimensionar);*
  *painel = `Flickable`+`ColumnLayout` de seções. Metadata via*
  *`getMapSpectraInfo()` (pts STS, bias, sweeps, datasets).*

## Portabilidade (Windows) — audit 2026-07-01

- [ ] **`file://` stripping quebra no Windows.** ~15 QML fazem
  `path.substring(7)` / `.replace("file://","")`. macOS
  `file:///Users/x`→`/Users/x` ✓; Windows `file:///C:/Users/x`→
  `/C:/Users/x` ✗ (barra antes da letra do drive → path inválido).
  Quebra TODOS os diálogos de abrir/salvar no Windows (import de
  mapa/imagem, load/save de projeto, workflow, export). Fix robusto:
  converter a URL no lado Python via `QUrl(url).toLocalFile()` (trata
  as duas plataformas) em vez de fatiar string. Afeta:
  MapEditorWorkstation, ImageWindowContent, HyperspectralControlPanel,
  IntegrationTool, MapViewerPanel, MapDiscretizerTool,
  MapProcessingTool, ImageSmoothingTool, NodeParameterEditor,
  LoadWorkflowDialog, GraphWindowContent, TableWindowContent.
- [ ] **Sem CI.** Não há `.github/workflows/`. Adicionar job
  `windows-latest` (+ `macos`) rodando `pytest` headless com
  `QT_QPA_PLATFORM=offscreen` daria validação Windows automática a
  cada push (pega import/erros de path; não pega render/interação).

## Project Browser

- [x] **Rolling text para legibilidade.** Quando o nome do
  dataset trunca, fazer rolar no hover.
  *Fix: o nome do item no `ProjectBrowser.qml` agora fica dentro
  de um `Item { clip: true }`; quando o texto realmente transborda
  e o mouse está em cima, um `SequentialAnimation on x` faz
  marquee (pausa → rola até o fim → pausa → volta, em loop). Sem
  hover/overflow continua elidido com "…". Reset de x ao sair.*
- [x] **Estrutura em árvore com pastas.** Permitir criar pastas
  para organizar datasets, com drag-and-drop.
  *Fix (Phases D1/D2, `30adc86` + `a6974ec`): árvore de pastas no
  backend (`getBrowserTree`/`createFolder`/`renameFolder`/
  `deleteFolder`/`moveItem`, persistida) + UI achatada em
  `ProjectBrowser.qml`. Drag-and-drop via hit-test no release
  (não DropAreas — `Drag.Automatic` segfaulta no PySide6/macOS) com
  drop por região estilo Finder e root como alvo real. Auto-filing
  de imports nas pastas por tipo. (Parte do DnD/auto-filing ainda
  UNCOMMITTED no working tree em 2026-06-03.)*

## Preferências e estética

- [ ] **Trocar de fonte não funciona.** Preview só muda ao
  escolher Helvetica; nada mais. A UI não é atualizada e a
  configuração não persiste.
  *Parcial: causa-raiz resolvida — `applyCurrentScheme()`
  recarregava o preset imutável e descartava as edições. Agora
  empurra a cópia editada via `setCurrentSchemeData()` e o backend
  persiste colors+font em preferences.json (`current_scheme_data`).
  A família de fonte é aplicada como fonte padrão do QApplication
  no startup (main.py), valendo p/ todo widget que não fixa
  `font.family`. FALTA p/ update ao vivo: a maioria dos `Text`
  fixa `font.pixelSize`/`font.family` literais — varrer e ligar
  esses aos props de tema (`fontFamily`/`fontSize*`).*
- [ ] **Tamanho de texto.** Muda o preview, não altera a UI, não
  persiste.
  *Parcial: agora persiste e atinge os props raiz `fontSize*`.
  Widgets que fixam `font.pixelSize: N` literal ainda não escalam
  — mesma varredura do item acima.*
- [ ] **Cores hard-coded no QML.** Trocar cores individuais nas
  preferências não tem efeito; as cores estão fixas nos
  ``Rectangle.color`` / ``Material.accent`` / etc.
  *Parcial: edições do `ColorEditor` agora persistem e disparam
  `colorSchemeChanged` → `applyColorScheme()` atualiza os props
  raiz (bgDark, accentPink, …). Widgets ligados aos props mudam;
  cores literais ("transparent", hex fixos) ainda não.*

## Funcionalidades básicas

- [ ] **Ctrl+Z incompleto.** Só desfaz operações de ferramentas
  explicitamente utilizadas (o que nem é destrutivo). Deletar
  itens e outras operações destrutivas não entram no undo
  stack.
  *Parcial: delete de dataset/rename já tinham undo; agora
  `deleteImage` e `deleteNote` (entidades em memória) também
  empilham undo (app_backend.py). FALTA: deletes baseados em
  arquivo (`deleteMap`/`deleteTable`/`deleteGraph`/`deleteOutput`)
  fazem `unlink()` no disco e não emitem sinal "added", então
  desfazê-los exige (a) mover p/ lixeira de sessão e (b) plumbing
  de refresh do project browser. Deixado como follow-up.*
- [x] **Fechar durante operação trava o programa.** Quando o
  usuário tenta fechar o programa enquanto está salvando ou
  rodando qualquer worker, o programa trava porque o workflow
  editor nunca fecha. Avisar (modal) que há trabalho em
  andamento e aguardar / cancelar.
  *Fix: `onClosing` em Main.qml intercepta o close quando
  `backend.isBusy`, abre `busyCloseDialog` (modal) com opções
  "Keep Working" / "Cancel & Quit". Confirmar cancela o worker
  (`backend.cancelAllOperations()` → `worker_manager.cancel_all` +
  `cancel_current`) e re-emite o close, que fecha as janelas de
  workflow normalmente.*

## Datasets grandes (>1 GB) — reportado 2026-07-14

- [x] **Autosave travava tudo por minutos.** Com um projeto de 1.2 GB o
  autosave re-serializava o projeto inteiro a cada 5 min (gzip-9 por
  array + `json.dumps` de uma string de vários GB segurando o GIL +
  gzip-9 do JSON inteiro de novo — recomprimindo base64 já comprimido)
  no MESMO worker das ferramentas, então qualquer operação (ex.
  derivada) ficava presa na fila atrás dele.
  *Fix: (1) thread de I/O dedicada (`TRANS-IOWorker` em worker.py,
  `submit_io`) — saves/autosaves/exports nunca mais bloqueiam tarefas
  interativas; (2) autosave dirty-aware (autosave_manager.py escuta
  `projectModifiedChanged`) — projeto sem mudanças = tick vira no-op;
  (3) save streams `json.dump` direto num `gzip.GzipFile` nível 1 (sem
  string gigante intermediária, sem dupla compressão cara) e autosave
  usa `fast=True` (gzip nível 0 — float64 espectral mal comprime em
  QUALQUER nível). Benchmark 417 MB: 6.4 s (autosave fast) / 35 s (save
  manual) vs ~42 s+ antes; round-trip de load verificado idêntico,
  formato HRT2 inalterado.*
- [x] **Cliques repetidos empilhavam a mesma operação.** Sem feedback
  de fila, cada clique em "Calculate Derivative" enfileirava um
  recompute inteiro; pior, `WorkerManager._task_callbacks` é chaveado
  por nome, então submissões duplicadas sobrescreviam os callbacks da
  task em voo (resultado descartado em silêncio).
  *Fix: `WorkerManager` ignora submissão cujo nome já está
  pendente/rodando (worker.py `_submit_to`); cancelamentos limpam a
  entrada para não bloquear re-submissões futuras.*
- [x] **Import escrevia CSVs na main thread.** `_on_file_loaded` /
  `_on_folder_loaded` gravavam cada dataset importado como CSV
  sincronamente no callback da main thread — em imports de GB a UI
  congelava pela duração da exportação.
  *Fix: `_persist_imported_datasets` (app_backend.py) enfileira o lote
  na thread de I/O com nome único sequencial.*
- [x] **Binding loop no DatasetComboBox.** `calculatedWidth` /
  `popupContentWidth` escreviam `TextMetrics.text` DENTRO do binding
  que lê `advanceWidth` de volta → loop detectado (spam no console) e
  re-varredura constante do modelo inteiro — caro com muitos datasets.
  *Fix: medir com `FontMetrics.advanceWidth(texto)` (chamada de
  função, sem dependência de propriedade) em DatasetComboBox.qml.*
- [x] **Fila de imports ficava mais lenta a cada pasta (superlinear).**
  Enfileirar 10 pastas MATRIX de uma vez: cada import terminava mais
  devagar que o anterior. Não era o loader (é stateless por chamada) —
  era trabalho de main thread proporcional ao projeto INTEIRO, repetido
  por entidade nova: (a) `ProjectBrowser.rebuildRows()` rodava a cada
  `imageAdded`/`mapCreated`/`noteAdded`/`dataLoaded`/`browserTreeChanged`,
  ou seja dezenas de reconstruções completas por import, cada uma com um
  `getDatasetInfo()` por dataset; (b) `linkDatasetsFromBackend` religava
  todos os datasets a cada import, com 2 travessias QML↔Python e um
  `linkedDatasetsChanged` POR dataset; (c) os TIFFs das imagens de scan
  eram gravados inline no callback. Além do custo direto, essa main
  thread ocupada rouba o GIL da thread do loader, atrasando os imports
  seguintes.
  *Fix: `rebuildRows()` vira agendamento (Timer 16 ms → `rebuildRowsNow()`),
  novo `getDatasetEntries()` em bulk substitui o `getDatasetInfo()` por
  dataset, `relinkDatasetsToMapEditor()` faz clear+link em Python com
  `beginLinkBatch`/`endLinkBatch` (1 sinal), relink coalescido por Timer
  em Main.qml, e `_absorb_dataset_images` enfileira os TIFFs na thread de
  I/O (`openImage` já grava sob demanda).*
- [x] **Import "travava" por horas sem carregar nada — arquivos no iCloud.**
  `Load 01-Jul-2026` rodou 4h sem terminar (log 2026-08-10 18:05→22:07).
  NÃO era o loader: com a pasta baixada, 18-Jun (4204 arq.) carrega em 2,1s.
  Diagnóstico: `~/Documents` está no iCloud Drive com "Optimize Mac Storage",
  e **303.144 dos 397.286 arquivos são placeholders** (st_size real,
  `st_blocks == 0`). Cada `read_bytes()` bloqueia até o macOS baixar o
  arquivo; `brctl status` mostrava o downloader falhando com
  `"Network Unavailable" (NSURLErrorDomain:-1009)`. Assinatura clássica:
  processo `sleeping`, **0% CPU**, RSS estável, um `.I(V)_mtrx` aberto —
  indistinguível de travamento. 4 pastas estão 100% não-baixadas.
  *Fix: pré-checagem `_check_downloaded` / `_count_dataless` em
  `_do_load_folder` — falha na hora com mensagem explicando o que fazer
  (Finder → Download Now / desligar Optimize Storage), em vez de bloquear a
  fila inteira atrás de uma pasta.*
- [x] **Import de pasta não tinha progresso nem cancelamento.** O caminho de
  diretório passava `progress_callback=None` para `_build_session`, então a
  fase mais longa (dezenas de milhares de curvas) não emitia nada, e
  `task.cancelled` só era checado ANTES de começar.
  *Fix: `load_from_directory(..., should_cancel=)` encaminha progresso
  por-curva (a cada 64) e checa cancelamento no mesmo ponto; retorna
  `(None, None)` ao cancelar e `_on_file_loaded`/`_on_folder_loaded`
  toleram `None`.*
- [ ] **`_build_images` custa ~26 s fixos** (30 arquivos de scan × ~0,87 s em
  `_image_via_a2m`, que reabre o header de 28 MB por imagem). Não é o
  travamento, mas é o maior custo fixo de uma sessão. Vale reusar o header
  já parseado.
- [ ] **`_detect_line_scans` é quadrático** (`_is_line` refaz `np.asarray`
  sobre todo o prefixo a cada crescimento do run): ×3,8 a cada 2× pontos.
  Irrelevante hoje (54 pontos), mas explode se uma sessão virar uma linha
  de milhares de pontos.
- [x] **Importar N pastas exigia N idas ao diálogo.** `FolderDialog` do
  Qt não tem multi-seleção.
  *Fix: `importFromFolder` — se a pasta escolhida não tem dados próprios
  mas as subpastas têm, cada subpasta com dados vira um import na fila
  (`_folder_has_data`). Escolher "STM UHV" enfileira as 10 pastas de dia.*
