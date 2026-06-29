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
