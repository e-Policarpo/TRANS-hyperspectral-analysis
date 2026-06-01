# Bughunt TRANS

Lista corrente de bugs e melhorias encontradas no uso real do TRANS.
Cada item começa não-resolvido (`- [ ]`); marque `- [x]` quando o fix
estiver no `Unified-UI` (e cole o hash do commit ao lado).

Última atualização: 2026-06-01.

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

- [ ] **Downsampling em gráficos densos.** Para que a UI não trave
  com curvas de >100k pontos.
  *Nota: o caminho QPainter (Phase 3) já tem `downsample` em
  `prepare_curve_xy` com `max_points=100_000`. Verificar se está
  realmente ativo no fluxo da usuária.*
- [ ] **Culling de dados fora da viewport.** Não desenhar segmentos
  que estão fora do `ax_rect`.
- [ ] **Area select para zoom mapeia coordenadas erradas.** O zoom
  resultante sai deslocado em relação ao retângulo selecionado.
- [ ] **Panning.** Adicionar pan dedicado nos gráficos.
  *Nota: o ViewBox da Phase 2 já tem `MOUSE_MODE_PAN`; verificar
  se a toolbar do `GraphWindowContent.qml` está expondo o toggle
  corretamente.*
- [ ] **Tabela ↔ spectral data.** Adicionar funcionalidade de
  converter uma tabela em spectral data (ou unificar os dois no
  backend mantendo separação organizacional no project browser).
- [ ] **Operações sobre gráficos não disparam.** Smoothing (e
  provavelmente outros botões) emite o log
  `Opened dataset … - Smoothed in embedded windows` mas o gráfico
  não é alterado. O backend processa, mas o resultado não chega
  ao canvas.
- [ ] **Toggle zoom/pan não funciona.** Pan continua em botão
  direito e zoom em botão esquerdo independentemente da seleção
  na toolbar; ambos mapeiam coordenadas erradas.
- [ ] **Posição inicial dos gráficos.** Deveria auto-centralizar /
  auto-fit os dados (todos os pontos visíveis) ao abrir uma nova
  janela.

## Sistema de Widgets

- [ ] **Zona de captura do mouse na janela inteira.** Hoje só a
  barra superior reage ao foco; o mouse dentro do conteúdo da
  janela não direciona os comandos para essa janela específica.
- [ ] **Ctrl+C / Ctrl+V** (mensagem cortada — copiar para tabelas?
  para gráficos? Confirmar escopo).

## Sistema de Imagens

- [ ] **Sensibilidade do scroll de zoom muito alta.** Diminuir o
  passo por wheel-tick.
- [ ] **Limite de zoom-out.** Não permitir reduzir abaixo do
  tamanho original da imagem.
- [ ] **Overlays de espectros duplicados.** Espectros estão sendo
  desenhados mais de uma vez no overlay; causa raiz não-óbvia.
- [ ] **Legenda fantasma no overlay.** Quando o usuário
  desseleciona um espectro na lista, a entrada correspondente
  fica na legenda.

## Aba de análise Hiperespectral

- [ ] **Mapas sem espectros associados ficam brancos ao ativar
  grid overlay.** Provavelmente um divide-by-zero ou um
  `imshow` com array vazio quando o map data ainda não tem
  espectros vinculados.
- [ ] **Overlays não aparecem nesta aba.** Os overlays de
  espectros (que funcionam no modo Spectral) não são herdados
  pela aba hiperespectral. Average spectrum também não puxa os
  gráficos.
- [ ] **Grid 1x1 aplica tamanho errado.** Quando o usuário coloca
  grid 1×1 explicitamente, o código aplica outro tamanho.
- [ ] **Average spectrum lê número errado de blocos.** Adicionar
  limpeza de cache ao trocar o tamanho do grid e reprocessar a
  média.
- [ ] **Suporte a espectros espacialmente resolvidos não-mapas.**
  Espectros pontuais e em linha (line scans) precisam ser
  reconhecidos além de mapas em área.
- [ ] **Zoom não funciona** nesta aba.
- [ ] **Crosshair invisível.** Selecionando a ferramenta
  crosshair, o cursor desaparece dentro do canvas.
- [ ] **Line profile.** Não lê a distância correta no eixo X e
  aceita perfis que saem da área da imagem.
- [ ] **NoneType ao abrir gráfico sem ponto associado.**
  ```
  An error occurred executing the property metacall WriteProperty
  on property "selectedCurveId" of QMLGraphCanvas(0x…)
  TypeError: 'NoneType' object is not callable
  ```

## Project Browser

- [ ] **Rolling text para legibilidade.** Quando o nome do
  dataset trunca, fazer rolar no hover.
- [ ] **Estrutura em árvore com pastas.** Permitir criar pastas
  para organizar datasets, com drag-and-drop.

## Preferências e estética

- [ ] **Trocar de fonte não funciona.** Preview só muda ao
  escolher Helvetica; nada mais. A UI não é atualizada e a
  configuração não persiste.
- [ ] **Tamanho de texto.** Muda o preview, não altera a UI, não
  persiste.
- [ ] **Cores hard-coded no QML.** Trocar cores individuais nas
  preferências não tem efeito; as cores estão fixas nos
  ``Rectangle.color`` / ``Material.accent`` / etc.

## Funcionalidades básicas

- [ ] **Ctrl+Z incompleto.** Só desfaz operações de ferramentas
  explicitamente utilizadas (o que nem é destrutivo). Deletar
  itens e outras operações destrutivas não entram no undo
  stack.
- [ ] **Fechar durante operação trava o programa.** Quando o
  usuário tenta fechar o programa enquanto está salvando ou
  rodando qualquer worker, o programa trava porque o workflow
  editor nunca fecha. Avisar (modal) que há trabalho em
  andamento e aguardar / cancelar.
