# Sistema de Gestão de Fiado — Etapas 1 e 2: Fundação + Login

## Correção: nota com pagamento misto lançava o valor errado (novidade)

- **Causa raiz**: é comum o cliente pagar parte da compra na hora
  (dinheiro/cartão) e só o restante ficar marcado na conta — a nota fiscal
  tem, nesse caso, mais de um `<detPag>` (um par forma de pagamento +
  valor por forma). O sistema só olhava se existia **algum** `tPag=05`
  (Crédito Loja) na nota pra decidir "é fiado", mas usava o **valor total
  da nota inteira** (`<vNF>`) como valor da compra — mesmo quando só uma
  parte era fiado de verdade. Confirmado com nota real: cliente pagou R$
  50,00 em dinheiro e R$ 16,84 ficou na conta (nota de R$ 66,84 no total)
  — o sistema lançaria os R$ 66,84 inteiros, cobrando R$ 50,00 a mais do
  que devido.
- **Correção**: `nfe_parser.ler_nfe` agora lê cada `<detPag>` como um par
  (forma de pagamento + valor daquela forma), soma só os valores com
  `tPag=05` (`NotaFiscalXml.valor_fiado`) e é esse valor — não o total da
  nota — que vira o valor da compra, tanto na lista de candidatos a
  importação quanto na compra criada de fato.
- **Nota rodada de novo**: as notas fiado já indexadas antes desta
  correção (ainda não importadas) são reprocessadas automaticamente na
  próxima varredura, pra recalcular o valor certo — não precisa fazer
  nada manualmente.
- Compras que **já foram importadas** antes desta correção, a partir de
  uma nota com pagamento misto, podem ter ficado com o valor maior que o
  devido — isso não é corrigido automaticamente (exigiria revisar cada
  caso manualmente); avise se quiser ajuda para identificar quais.

## Correção: valor de nota fora da faixa travava a indexação em lote (novidade)

- **Causa raiz**: alguma nota tem um valor total (`<vNF>`) fora da faixa que
  as colunas de valor do banco aceitam (`Numeric(12,2)` — até
  9.999.999.999,99) — dado corrompido/errado no próprio arquivo, não algo
  causado pelo sistema (o XML nunca é alterado, só lido). Isso só passou a
  aparecer depois da correção anterior (NFC-e sem cliente não é mais
  "inválida") — antes, esse arquivo específico provavelmente já era
  rejeitado mais cedo por falta de cliente identificado, então o sistema
  nunca chegava a ler o valor dele. Como a indexação grava em lotes de 200
  arquivos numa única transação, um valor assim fora da faixa fazia o
  banco rejeitar **o lote inteiro** — e como nada daquele lote ficava
  marcado como resolvido, a próxima varredura tentava o mesmo lote de
  novo, do mesmo jeito, travando sempre no mesmo lugar.
- **Correção**: `nfe_parser.ler_nfe` agora valida o valor total contra a
  faixa que o banco aceita — um valor fora da faixa faz o arquivo ser
  tratado como inválido (mesma categoria já usada para XML corrompido),
  em vez de tentar gravar e quebrar o lote inteiro. O resto do lote
  continua sendo processado normalmente.

## Compras quitadas saem da Ficha do Cliente, vão pro Histórico (novidade)

- **Causa raiz**: a Ficha do Cliente listava todas as compras do cliente
  juntas — abertas e já quitadas — diferenciadas só por um texto no final
  de cada linha. Como compra nunca é apagada do banco (só muda de status),
  um cliente antigo acumulava uma lista cada vez maior, quase toda já
  paga, misturada com o que realmente importa no dia a dia: o que ainda
  está em aberto.
- **Correção**: a lista "Compras em aberto" da Ficha do Cliente agora
  mostra só isso — compras em aberto. As já quitadas passaram a aparecer
  no **Histórico de Pagamentos**, junto do pagamento que as quitou (usando
  a ligação pagamento↔compra que o sistema já guardava internamente, até
  então usada só para o estorno saber o que reverter) — ao selecionar um
  pagamento na tabela, a lista abaixo mostra quais compras ele quitou e
  quanto foi aplicado em cada uma.
- O botão **"Ver Produtos"** (para compras vindas de XML importado) foi
  junto para o Histórico — antes só dava pra conferir os produtos de uma
  compra ainda em aberto na Ficha; agora também dá pra conferir os
  produtos de uma compra já quitada, a partir do pagamento que a fechou.
- O **Extrato** (impressão) também passou a listar só as compras em
  aberto — a pedido, para ficar consistente com a Ficha. O histórico de
  pagamentos impresso continua completo (inclusive estornados).
- Nada disso apaga ou esconde dado nenhum do banco — é só uma reorganização
  de onde cada informação aparece na tela.

## Correção: quase toda a pasta de XMLs sendo relida em toda varredura (novidade)

- **Causa raiz**: o leitor de XML (`nfe_parser.ler_nfe`) exigia um nome de
  cliente (`<dest><xNome>`) para considerar um arquivo "válido" — mas uma
  NFC-e de venda no balcão sem cliente identificado (o caso normal da
  imensa maioria das vendas de uma loja) não tem essa tag de jeito nenhum,
  mesmo sendo um XML completo e correto. Isso fazia esses arquivos caírem
  como "inválidos" e, pelo mecanismo de retry infinito (pensado para
  arquivo sendo gravado no meio da varredura, um caso transitório), serem
  reabertos e reprocessados em **toda** varredura futura, para sempre.
  Confirmado com dados reais de uma pasta com ~123 mil arquivos: **121.601
  deles** (98,9%) caíam nesse caso — cada clique em "Importar XMLs"
  reprocessava quase a pasta inteira.
- **Correção**: nome de cliente deixou de ser exigido para um XML ser
  considerado válido — continua sendo exigido só o que é realmente
  essencial e sempre presente em qualquer NF-e (chave de acesso e data de
  emissão). Um arquivo sem cliente agora é indexado normalmente como
  "válido, mas não-fiado" (mesmo tratamento que uma venda no cartão já
  recebia) e nunca mais reprocessado.
- **Custo único**: a primeira varredura depois desta correção ainda
  precisa abrir esses arquivos mais uma vez, para trocar o status deles no
  índice de "inválido" para "válido" — depois disso, ficam resolvidos de
  vez. Validado contra a pasta real de ~123 mil arquivos: 122.740 passaram
  a ser lidos com sucesso (só sobrou 1 com erro de sintaxe genuíno).

## Correção: erro "Multiple rows were found" ao trocar a pasta de XMLs (novidade)

- **Causa raiz**: o índice permanente de XMLs (`xml_indexados`) identifica
  cada arquivo pelo **caminho completo**, não pela chave da nota fiscal —
  proposital, para rastrear até arquivos inválidos (sem chave). Só que,
  quando a pasta de XMLs configurada muda de um caminho local para um
  caminho de rede/servidor que aponta para os **mesmos arquivos**, cada
  arquivo passa a ser enxergado com um caminho novo e o sistema o trata
  como se fosse um arquivo totalmente diferente — criando uma segunda
  linha no índice para a mesma nota fiscal (mesma chave, dois caminhos).
  Isso causava dois sintomas: a varredura reprocessava a pasta inteira de
  novo (parecendo travada, já que nenhum arquivo "batia" com o caminho
  novo) e a tela "Ver Produtos" quebrava com `Multiple rows were found
  when one or none are required.` ao encontrar duas linhas para a mesma
  chave.
- **Correção**: `xml_indexado_repository.inserir_lote` agora detecta,
  antes de gravar, quando uma chave já indexada aparece sob um caminho
  diferente — nesse caso, **atualiza a linha existente** com o novo
  caminho em vez de criar uma segunda. `buscar_por_chave` também ficou
  mais defensivo: mesmo que uma duplicata já exista (de antes desta
  correção), ele nunca mais quebra — sempre devolve a entrada mais
  recentemente atualizada, em vez de exigir exatamente uma linha.
- Nada disso lê, grava ou de qualquer forma altera os arquivos XML em
  si — a correção mexe só no índice interno (tabela `xml_indexados`) que
  o sistema usa para não precisar reabrir a pasta inteira a cada operação.
- Reprocessar a pasta inteira uma vez, na primeira varredura depois de
  trocar o caminho configurado, continua acontecendo (não tem como saber
  que é o "mesmo arquivo" sem reabri-lo pelo menos uma vez) — mas agora
  isso é seguro e não deixa duplicatas nem quebra nada depois.

## Plano B para criar o admin quando o Windows bloqueia o .exe (novidade)

- **Causa raiz**: executáveis do PyInstaller sem assinatura digital (como
  `CriarUsuarioAdmin.exe`) podem ser bloqueados pelo Windows SmartScreen ou
  pelo Defender como "app desconhecido/incompatível" em alguns
  computadores — um falso positivo comum, não é vírus de verdade, mas
  impede o programa de abrir até resolver.
- **Correção**: novo `criar_admin_emergencia.sql`, empacotado junto (o
  `build_exe.bat` já copia pra dentro de `dist\SistemaFiado`). Cria o
  usuário `admin` (senha temporária `admin123`) direto no banco via SQL —
  não depende de nenhum executável, só de `psql`/pgAdmin (os mesmos já
  necessários para `preparar_banco.bat`). Depois de logar, troque a senha
  pela própria tela "Usuários" do sistema (Administrador > Usuários >
  Redefinir senha) — dali em diante, todo o resto da gestão de usuários já
  funciona pela interface normal, sem precisar mais de SQL.
- Para um login/senha diferente do padrão, o hash da senha (formato
  Argon2, o mesmo algoritmo do sistema) pode ser gerado em qualquer
  computador que tenha o projeto e o `venv` instalados:
  `venv\Scripts\python.exe -c "from app.services.auth_service import gerar_hash_senha; print(gerar_hash_senha('SUA_SENHA'))"`

## Executável para criar o primeiro usuário administrador (novidade)

- **Causa raiz**: num banco de dados genuinamente novo, o `SistemaFiado.exe`
  cria as tabelas sozinho na primeira vez, mas a tabela de usuários fica
  vazia — e não existia nenhuma forma de criar o primeiro login sem ter
  Python instalado (a única opção era o script
  `app/scripts/criar_usuario_admin.py`, que só roda a partir do
  código-fonte).
- **Correção**: `fiado.spec` agora gera **dois** executáveis dentro da
  mesma pasta `dist\SistemaFiado`: `SistemaFiado.exe` (o programa, como
  antes) e `CriarUsuarioAdmin.exe` (ferramenta de linha de comando —
  pergunta nome, login e senha no terminal e cria o usuário). Os dois
  compartilham as mesmas bibliotecas (via `MERGE` do PyInstaller), sem
  duplicar espaço em disco. `CriarUsuarioAdmin.exe` também garante que as
  tabelas do banco existam antes de criar o usuário, então pode ser
  rodado como primeiro passo, mesmo num banco totalmente vazio.
- **Fluxo de instalação num servidor novo**: `preparar_banco.bat` (cria o
  banco/usuário/schema no PostgreSQL) → `CriarUsuarioAdmin.exe` (cria o
  primeiro login) → `SistemaFiado.exe` (usar o sistema). O
  `preparar_banco.bat` já pergunta, ao final, se quer rodar o
  `CriarUsuarioAdmin.exe` na hora.

## Script para preparar um servidor PostgreSQL novo (novidade)

- **Causa raiz**: ao instalar o sistema num servidor PostgreSQL genuinamente
  novo (loja nova, ou servidor de testes), era preciso criar manualmente o
  banco, o usuário e o schema `public` via `psql`/pgAdmin antes de abrir o
  `.exe` — passo a passo fácil de esquecer ou errar (ex.: aconteceu um erro
  `InvalidSchemaName` por o schema `public` não existir no banco novo).
- **Correção**: dois arquivos novos, `preparar_banco.bat` e
  `provisionar_banco.sql`, agora ficam junto do `.exe` (o `build_exe.bat`
  já copia os dois pra dentro de `dist\SistemaFiado` automaticamente). O
  `.bat` lê os dados de conexão direto do `.env` já preenchido, pede só a
  senha do administrador do PostgreSQL (`postgres`) e cria o que faltar —
  usuário, banco de dados e schema `public` com as permissões certas.
  Idempotente: pode rodar de novo sem risco, só cria o que ainda não
  existe, nunca apaga nada.
- **Só é necessário uma vez por servidor PostgreSQL**, não por computador —
  se o computador novo só vai se conectar a um servidor que os outros
  computadores da loja já usam, basta configurar o `.env` com os mesmos
  dados e abrir o `SistemaFiado.exe` direto (o próprio sistema cria as
  tabelas sozinho na primeira vez, ver "Criação Automática do Esquema do
  Banco" mais abaixo).

## Correção: venda no cartão de crédito sendo confundida com fiado (novidade)

- **Causa raiz**: nem toda nota com natureza de operação `natOp="Venda a
  prazo"` é fiado de verdade — vendas pagas no cartão de crédito também
  usam essa mesma natureza de operação neste sistema de emissão. O sistema
  usava só o `natOp` para decidir o que é fiado, então clientes que nunca
  compraram fiado (só passaram o nome no cartão) apareciam como candidatos
  a importação. Confirmado com dado real: a cliente MARIA INES RIBEIRO tem
  17 notas "Venda a prazo", nenhuma com `tPag=05` (todas no cartão) — ou
  seja, zero fiado de verdade, mas todas seriam importadas como se fossem.
- **Correção**: o campo `<tPag>` (forma de pagamento) de cada nota agora é
  lido do XML. Uma nota só é considerada fiado (`eh_fiado`) quando **as
  duas condições** são verdadeiras: `natOp="Venda a prazo"` **e**
  `tPag="05"` (Crédito Loja — o código oficial da SEFAZ para esse tipo de
  venda). `app/utils/nfe_parser.py`, `app/models/xml_indexado.py` e
  `app/repositories/xml_indexado_repository.py` foram atualizados para usar
  esse novo campo `eh_fiado` (em vez de `eh_venda_a_prazo` sozinho) na
  listagem de candidatos a importação.
- **Migração necessária**: rode `alembic upgrade head` (o
  `build_exe.bat`/instalador já faz isso automaticamente). A migração
  esvazia a tabela `xml_indexados` — é só um cache de performance, nunca a
  fonte da verdade, então isso é seguro. Depois de atualizar, use "Importar
  XMLs Agora" (ou "Ver Produtos") pelo menos uma vez em cada tela de
  cliente/pasta para que o índice seja reconstruído do zero com a lógica
  corrigida.
- **Atenção**: esta correção vale só para o índice e para novas
  importações a partir de agora. Compras que já foram importadas
  incorretamente como fiado antes desta correção (uma venda no cartão
  importada por engano) **não são desfeitas automaticamente** — se
  desconfiar de alguma compra de um cliente que não costuma comprar fiado,
  vale conferir manualmente e excluir se for o caso.

## Impressão adaptada para impressora térmica de 80mm (novidade)

- **Causa raiz**: o Recibo de Pagamento e o Extrato do Cliente imprimiam
  em página A4 (padrão do Qt), com tabelas largas de várias colunas — não
  fazia sentido numa impressora térmica não-fiscal de bobina de 80mm
  (modelo em uso: Elgin i9), ficando confuso e cortado.
- **Correção**: `app/utils/impressao.py` agora configura a página da
  impressora com 80mm de largura e margens pequenas (3mm), com a altura
  calculada a partir do conteúdo real de cada documento (bobina contínua
  não tem altura fixa como papel A4 — a impressão para exatamente onde o
  conteúdo termina, sem desperdiçar bobina). `app/utils/documentos.py`
  trocou as tabelas de várias colunas por um layout empilhado (data e
  valor numa linha, status na linha seguinte), compatível com a largura
  estreita. Nomes de cliente/observações agora passam por *escape* de
  HTML, para nunca quebrar o documento se contiverem caracteres como `&`
  ou `<`.
- Se a impressora não for exatamente 80mm de largura útil no futuro
  (trocar de modelo, por exemplo), os números-chave estão isolados em
  `_LARGURA_PAPEL_MM`/`_MARGEM_MM`, no topo de `impressao.py`.

## Índice permanente de XMLs, para pastas com dezenas/centenas de milhares de arquivos (novidade)

- **Causa raiz**: mesmo rodando em segundo plano e com feedback de
  progresso, uma pasta de XMLs muito grande (relatado: ~100-200 mil
  arquivos, vários computadores da rede acessando a mesma pasta) torna
  inviável reler a pasta inteira do zero a cada "Ver Produtos"/"Importar
  XMLs Agora" — mesmo a alguns milissegundos por arquivo, o total soma
  minutos.
- **Correção**: nova tabela `xml_indexados` (compartilhada via PostgreSQL,
  como todo o resto do sistema) guarda os dados já extraídos de cada
  arquivo processado (chave, natureza da operação, cliente, valor, data).
  A partir da segunda vez que **qualquer computador da rede** varre a
  pasta, uma nova varredura só abre e interpreta os arquivos que ainda não
  constam no índice — arquivos já vistos (por este ou por outro
  computador) nunca são reabertos. A primeira varredura de uma pasta muito
  grande ainda precisa processar tudo uma vez (não tem como evitar — é
  quando o índice é construído), mas esse custo só é pago uma única vez no
  total da rede, não a cada clique.
- A indexação grava em lotes de 200 arquivos por vez (não tudo numa
  transação só): se for interrompida no meio (fechar o programa, desligar
  o computador), o progresso feito até ali não se perde — a próxima
  varredura retoma dali, sem refazer os lotes já gravados.
- O feedback de progresso ("Verificando arquivo X de Y...") agora reflete
  só os arquivos **novos** desta varredura, não o total da pasta — em uma
  pasta já indexada, uma varredura de rotina (poucos arquivos novos desde
  a última vez) deve ser praticamente instantânea.

## Correção: telas de XML ficavam "presas" em pastas com muitos arquivos (novidade)

- **Causa raiz**: a correção anterior (rodar a varredura de XML em
  `QThread`, para não travar a interface) tinha uma falha de design — para
  evitar o crash de fechar a janela com a thread ainda ativa, o fechamento
  ficava bloqueado (ou, numa tentativa anterior, esperava até 5s e depois
  fechava mesmo assim, reintroduzindo o crash). Numa pasta com centenas ou
  milhares de XMLs (varredura genuinamente demorada, ainda mais com
  antivírus interceptando cada abertura de arquivo), isso deixava a tela
  "Ver Produtos"/"Importar XMLs" parecendo travada para sempre, sem
  nenhuma forma de cancelar.
- **Correção definitiva**: `ImportarXmlDialog` e a Ficha do Cliente agora
  podem ser fechadas a qualquer momento, mesmo com a varredura ainda
  rodando — a `QThread` não fica mais presa ao ciclo de vida da janela
  (roda sem "pai" Qt) e se encerra sozinha quando termina; se a janela já
  tiver sido fechada nesse meio-tempo, o resultado é descartado
  silenciosamente. Nenhuma espera bloqueante em lugar nenhum do app.
- **Feedback de progresso**: `listar_candidatos_importacao` e
  `obter_produtos` (em `xml_importacao_service.py`) agora aceitam um
  callback `progresso(atual, total)`, chamado a cada arquivo verificado —
  as telas mostram "Verificando arquivo X de Y..." durante a varredura,
  em vez de uma mensagem estática indistinguível de travamento.

## Correção: Telas de XML travando o programa + leitura de XML mais rápida (novidade)

- **Causa raiz**: `ImportarXmlDialog` (Configurações → Importar XMLs Agora,
  e o aviso automático de XMLs pendentes ao abrir o sistema) varria a
  pasta de XMLs, fazia o parse de cada arquivo e consultava o banco
  **direto na thread da interface**, sem `QThread` — travava a tela até
  terminar, pior quanto mais XMLs acumulados na pasta. O mesmo valia para
  "Ver Produtos" antes da correção anterior a esta.
- **Correção 1 (nunca mais trava)**: `ImportarXmlDialog` agora varre a
  pasta e confirma a importação em `QThread`s próprias
  (`_ListarCandidatosWorker`/`_ImportarWorker`, mesmo padrão já usado por
  "Ver Produtos"), com "Varrendo..."/"Importando..." como feedback visual
  e o botão "Fechar" desabilitado durante a operação (evita o crash de
  fechar a janela com uma `QThread` ainda ativa).
- **Correção 2 (leitura mais rápida)**: `app/utils/nfe_parser.py` trocou
  `xml.etree.ElementTree` (biblioteca padrão do Python) por
  `lxml.etree.iterparse` (nova dependência) em `ler_nfe` e
  `ler_chave_rapida` — leitura incremental, evento a evento, que nunca
  carrega o XML inteiro em memória (cada elemento é descartado assim que
  processado) e roda sobre a libxml2 (C), bem mais rápida que a biblioteca
  padrão em Python puro. Reduz o tempo de cada varredura da pasta de XMLs,
  mesmo já rodando em segundo plano.
- Também corrigido, na mesma leva: erros de negócio (`ValueError`) que as
  telas relacionadas a XML lançavam (ex.: "arquivo não encontrado na pasta
  configurada") estavam sendo mostrados como um genérico "Erro
  inesperado" em vez da mensagem real — a checagem `except ErroDeNegocio`
  não capturava `ValueError` (esse mesmo ajuste foi replicado em todas as
  telas do sistema, não só nas de XML).

## Exportação em Excel, Lembretes por WhatsApp, Recibo/Extrato e Tema Escuro (novidade)

- **Exportação em Excel (`.xlsx`) do Saldo em Aberto**: além do CSV já
  existente, `Histórico e Relatórios → Saldo em Aberto` agora tem um botão
  "Exportar Excel", com cabeçalho em negrito, largura de coluna ajustada,
  valores em formato moeda e uma linha de total. Usa `openpyxl` (nova
  dependência, listada em `requirements.txt`).
- **Lembretes de saldo em aberto via WhatsApp** (aba "Lembretes", dentro de
  Histórico e Relatórios): lista clientes com compras em aberto há mais de
  N dias (padrão 30 — como o fiado não tem data de vencimento própria, a
  data da compra é usada como referência de atraso). O botão "Enviar
  Lembrete" abre um diálogo com uma mensagem padrão editável e um botão
  "Abrir no WhatsApp", que usa um link `wa.me` (click-to-chat) para abrir a
  conversa já preenchida — **não envia nada sozinho**: não existe
  integração com nenhuma API paga de WhatsApp/SMS (exigiria credenciais e
  conta comercial que o sistema não tem), então o envio final continua
  sendo uma ação manual do usuário dentro do WhatsApp.
- **Recibo de pagamento e extrato do cliente**: usando `QtPrintSupport`
  (já incluso no PySide6, mesmo padrão do `QtCharts` do painel de início —
  nenhuma dependência nova). Ao confirmar um pagamento em Receber Conta, a
  mensagem de sucesso ganhou um botão "Imprimir Recibo", que abre uma
  pré-visualização de impressão do comprovante. Na Ficha do Cliente, o
  novo botão "Extrato" mostra a pré-visualização de um documento com dados
  cadastrais, todas as compras e todos os pagamentos (inclusive
  estornados). Em ambos os casos, o usuário pode imprimir de verdade ou
  "imprimir" em PDF através de uma impressora virtual.
- **Tema escuro configurável**: `Configurações → Tema` deixou de ser
  informativo — agora tem um seletor Claro/Escuro de verdade, salvo como
  configuração global (mesmo padrão do modo de data padrão). O tema é
  aplicado uma única vez, na inicialização (`app/main.py`, via
  `QApplication.setStyleSheet`), então a troca só tem efeito depois de
  reiniciar o sistema — mesmo aviso já usado para a configuração de
  conexão com o banco.

## Etapa 1 — Fundação

Estrutura de pastas, configuração, conexão com o PostgreSQL (SQLAlchemy +
psycopg), modelos de dados (ORM) e setup do Alembic para migrações.

## Correção: Import Circular na Ficha do Cliente (novidade)

- **Bug encontrado**: `buscar_cliente_view.py` importava `ficha_cliente_view.py`,
  que por sua vez importava `adicionar_compra_view.py` e
  `receber_conta_view.py` — e esses dois importavam de volta um
  componente interno (`_BuscaClienteWorker`) de dentro de
  `buscar_cliente_view.py`, fechando um ciclo de import.
- **Correção**: esse worker de busca (usado pelos três lugares) foi
  extraído para um módulo próprio, `app/views/busca_cliente_worker.py`
  (classe `BuscaClienteWorker`, agora pública), que não depende de
  nenhuma dessas telas — quebra o ciclo. Rodei um verificador dedicado de
  ciclos de import em todo o projeto depois da correção; não sobrou
  nenhum outro.

## Criação Automática do Esquema do Banco (novidade)

Instalar em um computador novo (banco vazio) **não exige mais rodar
`alembic upgrade head` manualmente** — o sistema faz isso sozinho ao
abrir:

- **Banco vazio**: todas as tabelas são criadas diretamente a partir dos
  modelos atuais (`Base.metadata.create_all`), e o controle de versão do
  Alembic é marcado como atualizado — não depende de quais arquivos de
  migração foram gerados até agora.
- **Banco já existente**: continua aplicando só as migrações pendentes
  (`alembic upgrade head`), sem mexer nos dados já cadastrados.
- Falhas (ex.: usuário do banco sem permissão para criar tabelas)
  mostram um erro claro na tela, em vez de travar ou falhar silenciosamente.

**Atenção — só para os computadores que JÁ têm um banco com dados**: como
esse caminho ("banco já existente") depende dos arquivos de migração
reais que você gerou ao longo do projeto (`alembic revision --autogenerate`,
guardados em `app/database/migrations/versions/`), confirme que esses
arquivos ainda estão na sua cópia do projeto antes de gerar um `.exe`
novo — se algum zip mais recente tiver sobrescrito essa pasta, me avise
que eu ajudo a recuperar. Isso não afeta computadores novos (banco
vazio), que já funcionam de qualquer forma com a criação automática.

`fiado.spec` foi atualizado para empacotar `alembic.ini` e a pasta de
migrações dentro do `.exe` — se você já gerou o executável antes, rode
`build_exe.bat` de novo para incluir essa novidade.

## Correção: "Acessar Produtos" lento e travando o programa (novidade)

- **Causa**: duplo clique numa compra vinda de XML (na Ficha do Cliente)
  varria a pasta de XMLs inteira, fazendo o parse **completo** de cada
  arquivo até achar o certo — direto na thread da interface, travando a
  tela até terminar. Com centenas de XMLs na pasta, ficava lento e
  perceptível como travamento.
- **Correção 1 (mais rápido)**: nova função `ler_chave_rapida` em
  `nfe_parser.py`, que lê só a chave de acesso de cada arquivo (parada
  antecipada, sem interpretar produtos/totais) — o parse completo agora
  só acontece no único arquivo que realmente bate com a chave procurada.
- **Correção 2 (nunca mais trava)**: essa busca agora roda em uma
  `QThread` separada (`ObterProdutosWorker`), então mesmo que demore, a
  interface continua respondendo normalmente.

## Testes Automatizados (novidade)

Suíte com `pytest`, em duas categorias:

- **Testes puros** (`tests/test_text_normalizer.py`, `tests/test_nfe_parser.py`):
  não tocam banco nem Qt. **Já rodei estes de verdade** (com um executor
  próprio, já que este ambiente de desenvolvimento não tem `pytest`
  instalado) — os 15 testes passaram. No seu computador, rodam com
  `pytest` normalmente.
- **Testes de integração** (`tests/test_pagamento_service_fifo.py`,
  `tests/test_cliente_service.py`, `tests/test_auth_e_permissoes.py`):
  exercitam a camada de serviço de verdade contra o PostgreSQL — cobrem a
  lógica FIFO/Resto/estorno (inclusive o bloqueio de estorno quando o
  Resto já foi pago), busca/ranking, mesclagem de duplicados e
  permissões (admin x funcionário). **Não rodei estes** (não tenho
  PostgreSQL neste ambiente) — revisei cada assinatura de função chamada
  contra o código real, mas a validação final só acontece rodando de
  verdade no seu computador.

### Como rodar

```bash
pip install -r requirements-test.txt

# só os testes puros (não toca no banco):
pytest

# tudo, incluindo os testes de integração — aponte o .env para um banco
# de TESTES descartável antes de rodar isto, não para o banco de produção
# da loja, já que esses testes criam e apagam dados de verdade:
# Linux/Mac
RODAR_TESTES_INTEGRACAO=1 pytest
# Windows (PowerShell)
$env:RODAR_TESTES_INTEGRACAO="1"; pytest
```

Os testes de integração limpam os dados que criam (clientes/usuários de
teste, com nomes começando em "Teste Automatizado"/"teste_"), mesmo que
o teste falhe no meio.

## Log de Login/Logout (novidade)

- Reaproveita a tabela `historico_alteracoes` já existente (entidade
  "Usuario", ações `login`/`logout`) — aparece na aba **Histórico e
  Relatórios → Histórico de Alterações**, filtrando por "Usuario", junto
  com criação/edição/redefinição de senha de usuários. Nenhuma tabela ou
  tela nova.
- Logout é registrado de forma centralizada no `closeEvent` da janela
  principal — cobre o botão "Sair", o atalho `Ctrl+Q` e o "X" da janela,
  não só um desses caminhos.
- Se a gravação do login/logout falhar (ex.: banco fora do ar), o
  login/logout em si não é bloqueado — só fica registrado no arquivo de
  log.

## Ícones + Painel de Início (novidade)

- **Ícones em todos os botões do sistema** (`pytablericons`, conjunto
  Tabler Icons, estilo *outline*, paleta preto/cinza) — o texto de cada
  botão continua sempre presente, o ícone é só um complemento visual.
  `app/utils/icons.py` centraliza o carregamento, com *fallback* seguro:
  se algum nome de ícone não existir na biblioteca, o botão simplesmente
  fica sem ícone (nunca trava a aplicação). Abas da janela principal
  também ganharam ícone.
- **Nova aba "Início"** (primeira aba, só para Administrador — para os
  demais usuários, a aba nem aparece): painel estilo *dashboard*, com
  seletor de período (padrão: mês atual) e gráficos via
  `PySide6.QtCharts` (já incluso na instalação do PySide6, sem
  dependência nova):
  - **Maior Valor Gasto no Período** — clientes que mais gastaram (soma
    de compras).
  - **Mais Contas Lançadas no Período** — clientes que mais vezes
    compraram (quantidade de lançamentos, não valor).
  - **Evolução de Vendas** — total vendido por mês, últimos 6 meses.
  - **Total em Aberto (Geral)** — soma de tudo que está em aberto no
    negócio.
  - **Clientes com Maior Saldo em Aberto** — quem mais deve atualmente
    (não depende do período selecionado, é sempre a situação atual).

## Gerando o executável Windows (.exe) (novidade)

Não depende mais de Python instalado no computador de cada funcionário —
basta copiar uma pasta e rodar o `.exe`. **A geração do executável precisa
ser feita em um computador Windows** (o PyInstaller não compila de forma
cruzada a partir de Linux/Mac).

### Passo a passo

1. Copie a pasta inteira do projeto para um computador Windows com Python
   3.13 instalado.
2. Dentro da pasta do projeto, dê duplo clique em **`build_exe.bat`** (ou
   rode pelo terminal). Ele cria um ambiente virtual, instala as
   dependências (incluindo o PyInstaller) e gera o executável — pode
   demorar alguns minutos na primeira vez.
3. Ao terminar, o executável estará em `dist\SistemaFiado\SistemaFiado.exe`.
4. **Copie a pasta `dist\SistemaFiado` inteira** (não só o `.exe`) para
   cada computador da rede que for usar o sistema.
5. Em cada computador, copie `.env.example` para dentro dessa mesma pasta,
   renomeie para `.env` e preencha com os dados do servidor PostgreSQL da
   rede (mesmo `.env` de sempre — os dados de conexão costumam ser
   idênticos em todos os computadores, já que todos apontam para o mesmo
   servidor).
6. Dê duplo clique em `SistemaFiado.exe` para abrir o sistema.

### O que muda ao rodar como .exe

- `app/config/settings.py` foi ajustado para detectar quando está rodando
  "congelado" (`.exe`) e usar a pasta onde o executável está (em vez da
  estrutura de pastas do código-fonte) como base para `.env`, backups e
  logs — essas pastas continuam se chamando `app/backups` e `app/logs`,
  só que criadas automaticamente ao lado do `.exe` na primeira execução.
- `pg_dump`/`psql` (backup e restauração) continuam precisando estar
  instalados e no PATH de cada computador que for usá-los — isso é
  independente do `.exe` (são ferramentas do PostgreSQL, não do Python).
- A migração do banco (`alembic upgrade head`) continua sendo feita a
  partir do código-fonte (por quem administra o servidor), não pelo
  `.exe` — os funcionários que só usam o sistema no dia a dia nunca
  precisam mexer com isso.

### Arquivos usados na geração do executável

- `fiado.spec` — especificação do PyInstaller (módulos que precisam ser
  incluídos manualmente, como o dialeto PostgreSQL do SQLAlchemy e o
  driver `psycopg`, que são carregados dinamicamente e por isso o
  PyInstaller não os detecta sozinho).
- `build_exe.bat` — automatiza os passos acima em um único comando.

## Correção: Restauração falhando com "tipo já existe" (novidade)

- **Bug encontrado**: o `--clean` do `pg_dump` apaga objeto por objeto, na
  ordem que ele calcula — mas se o banco já tinha sobras de uma
  restauração anterior mal-sucedida (comum antes da correção anterior,
  que não interrompia em erro), a ordem podia não bater com o que
  realmente existia, e um `CREATE TYPE` rodava antes do `DROP TYPE`
  correspondente ter sido aplicado com sucesso.
- **Correção definitiva**: antes de aplicar qualquer restauração, o
  sistema agora apaga o schema `public` inteiro e recria vazio (`DROP
  SCHEMA public CASCADE` + `CREATE SCHEMA public`) — garante um estado
  100% limpo sempre, não importa o que tenha sobrado de tentativas
  anteriores. Isso também corrige o backup que estava travado: a próxima
  tentativa de restauração já deve funcionar, mesmo com o banco no estado
  atual.

## Correção: Restauração de Backup não desfazia alterações (novidade)

- **Bug encontrado**: o `pg_dump` gerava o backup sem `--clean`, então ao
  restaurar sobre um banco que já tinha dados (sempre o caso), o `psql`
  tentava *inserir* linhas que já existiam (mesmo ID) — o comando falhava
  silenciosamente por linha, sem avisar nada, e por isso a restauração
  parecia "não fazer nada" (ex.: uma conta excluída continuava excluída).
- **Correção**: `pg_dump` agora roda com `--clean --if-exists` (o backup
  passa a incluir os comandos para apagar os dados antigos antes de
  recriá-los) e `psql` roda com `-v ON_ERROR_STOP=1` (qualquer erro real
  de restauração agora interrompe o processo e é reportado, em vez de
  ser ignorado). **Só vale para backups gerados a partir de agora** — um
  backup antigo, gerado antes desta correção, continua sem os comandos de
  limpeza.

## Correção + Mesclagem de Clientes Duplicados (novidade)

- **Causa raiz corrigida**: dentro de um mesmo lote de importação de XML,
  se vários XMLs tiverem o mesmo nome de cliente e nenhum bater com
  cadastro já existente, o sistema agora cria **um único** cliente novo e
  reaproveita para os demais do lote — antes, cada XML gerava um cadastro
  separado.
- **Ferramenta de limpeza** (Configurações → "Verificar Clientes
  Duplicados"): agrupa clientes ativos com o mesmo nome principal
  (ignorando acento/maiúscula), permite escolher qual cadastro fica como
  principal por grupo e move as compras/pagamentos dos duplicados para
  ele. Os duplicados ficam inativos (exclusão lógica — nada é apagado).

## Etapa 10 — Integração com XML de NF-e (Venda a Prazo) (novidade)

- **Nova coluna** `Cliente.confirmado` (booleano, `True` por padrão). Clientes
  criados automaticamente pela importação de XML nascem com `False` e
  aparecem em **vermelho** na Busca de Cliente até serem confirmados.
  **Requer nova migração** (veja abaixo).
- `app/utils/nfe_parser.py`: leitura (nunca escrita) de XMLs de NF-e —
  testado com um XML real de exemplo. Identifica "venda a prazo" pelo
  campo `<ide><natOp>`, extrai nome do destinatário, data de emissão,
  valor total e produtos (nome, quantidade, valor).
- **Importação**: tela de revisão (`Configurações → Importar XMLs Agora`,
  ou automaticamente perguntado ao abrir o sistema, se houver XMLs
  pendentes) que lista os XMLs de venda a prazo ainda não importados,
  resolve o cliente correspondente (mesma lógica de busca já usada em
  Buscar Cliente) e deixa o usuário escolher manualmente quando há mais de
  um candidato — ou confirmar a criação de um cliente novo.
- Deduplicação pela **chave de acesso da NF-e** (não pelo nome do arquivo),
  guardada em `Compra.origem_nfe_xml` (campo já reservado desde a etapa 1).
- Na Ficha do Cliente, compras vindas de XML mostram um ícone 📄 — duplo
  clique reabre o XML original (nunca duplicado no banco) e mostra os
  produtos daquela nota.
- Cliente pendente de confirmação: ao abrir sua ficha, o sistema pergunta
  se o cadastro deve ser confirmado.
- Pasta de XMLs é uma configuração global, editável em Configurações
  (mesmo padrão da pasta de backup).

### Nova migração necessária

```bash
alembic revision --autogenerate -m "adiciona coluna confirmado em clientes"
alembic upgrade head
```

## Etapa 9 — Estorno de Pagamento + Atalhos de Teclado (novidade)

- **Correção de inconsistência**: `cliente_service.excluir_cliente` agora
  exige Administrador — a tabela de permissões aprovada na etapa 1 já
  previa isso, mas a checagem não tinha sido implementada até aqui.
- **Estorno de pagamento** (Administrador): reabre as compras quitadas por
  aquele pagamento. Só é permitido quando a eventual conta "Resto" gerada
  por ele ainda não tiver sido tocada por um pagamento posterior — nesse
  caso, o estorno é bloqueado com uma mensagem explicando o motivo (evita
  inconsistência com o que já aconteceu depois).
- Botão **Histórico** da Ficha do Cliente agora abre de verdade: lista os
  pagamentos do cliente (inclusive estornados) e permite estornar (só
  aparece o botão de estornar para Administrador).
- **Atalhos de teclado**: `Ctrl+N` → aba Cadastrar Cliente, `Ctrl+F` → aba
  Buscar Cliente, `Ctrl+Q` → sair do sistema.

## Etapa 8 — Histórico, Relatórios e Configurações (novidade)

- Aba **Histórico e Relatórios** (Administrador), com 3 sub-abas:
  - **Histórico de Alterações**: consulta `historico_alteracoes` (alimentada
    desde a etapa 2), com filtro por entidade.
  - **Log de Erros**: consulta `log_erros`; duplo clique mostra o
    stacktrace completo.
  - **Saldo em Aberto**: relatório de clientes com conta em aberto, com
    **exportação em CSV** (abre direto no Excel; não foi adicionada a
    biblioteca `openpyxl` para gerar `.xlsx` de verdade — se precisar
    disso especificamente, é só pedir).
- Aba **Configurações** (Administrador): edição do modo de data padrão
  (reaproveitando o `configuracao_service` da etapa 5). Conexão com o
  banco e tema aparecem apenas de forma informativa (conexão exige
  reiniciar o sistema; tema escuro segue reservado para o futuro).

## Etapa 7 — Backup (novidade)

- Backup via `pg_dump` (compactado em `.zip`) e restauração via `psql`,
  chamados por `subprocess`. **Exige que `pg_dump` e `psql` estejam
  instalados e no PATH** do computador (fazem parte da instalação cliente
  padrão do PostgreSQL).
- Backup automático diário: verificado ao abrir o sistema e a cada hora
  enquanto ele estiver aberto (não depende de agendador do sistema
  operacional). A data do último backup automático fica salva na tabela
  `configuracoes`. Falhas nessa verificação silenciosa (ex.: `pg_dump` não
  encontrado) só vão para o arquivo de log — não interrompem o usuário.
- Tela **Backup** (aba visível só para Administrador): escolher pasta de
  destino, fazer backup manual, restaurar a partir de um `.zip` (com
  confirmação, já que substitui os dados atuais).
- Pasta de backup também é uma configuração global (`configuracoes`),
  reaproveitando o mesmo padrão da data padrão.

## Etapa 6 — Receber Conta (novidade)

- Lógica de quitação **FIFO**: a compra em aberto mais antiga é sempre
  quitada primeiro. Uma compra em aberto é sempre integralmente devida —
  quando um pagamento cobre só parte dela, ela é marcada como quitada e o
  valor restante vira uma nova compra "Resto" (`eh_resto=True`,
  com referência à compra de origem para auditoria).
- Cada aplicação de pagamento em uma compra é registrada em
  `pagamento_compra` (quanto de cada pagamento quitou cada compra) — base
  para uma futura função de estorno.
- Validação: o valor pago não pode exceder o total em aberto do cliente.
- Tela **Receber Conta**: mesmo padrão de busca/pré-seleção da tela
  Adicionar Compra. Mostra as compras em aberto e o total antes de
  confirmar; campo "Recebido por" preenchido automaticamente com o
  usuário logado (não editável); observações opcionais; data com o mesmo
  `date_utils` (editável).

## Etapa 5 — Adicionar Compra (novidade)

- Nova tabela `configuracoes` (chave/valor), compartilhada por toda a rede
  via PostgreSQL — guarda o modo de data padrão ("dia atual" / "dia
  anterior", configuração global). **Requer nova migração** (veja abaixo).
- `app/utils/date_utils.py`: calcula a data sugerida no formulário de
  compra a partir dessa configuração (padrão de fábrica: "dia anterior").
  A data sempre pode ser alterada manualmente.
- Tela **Adicionar Compra**: acessível pela aba direta (busca o cliente
  primeiro, mesmo padrão de busca com debounce/thread já usado na Busca de
  Cliente) ou pelo botão da Ficha do Cliente (cliente já vem
  pré-selecionado). Campos: valor, data e comprador (opcional, lista
  vinda dos compradores cadastrados daquele cliente).
- O campo `origem_nfe_xml` do modelo `Compra` (criado na etapa 1) segue
  reservado, sem uso, para a futura integração com XML de NF-e/NFC-e.

### Nova migração necessária

```bash
alembic revision --autogenerate -m "adiciona tabela de configuracoes"
alembic upgrade head
```

## Etapa 4 — Busca de Cliente + Ficha do Cliente (novidade)

- Tela **Buscar Cliente**: busca com *debounce* (300ms) executada em uma
  `QThread` separada (não trava a interface), ignorando acento/maiúscula/
  espaços extras. Ranking: nome principal que começa com o termo → nome
  alternativo que começa com o termo → nome principal que contém → nome
  alternativo que contém (compradores não entram na busca). Resultados
  batendo por nome alternativo aparecem como "Nome Principal (Apelido)".
- Duplo clique em um resultado abre a **Ficha do Cliente**: dados
  cadastrais, lista de compras (ainda sempre vazia até a etapa 5) e total
  em aberto, com os 6 botões do requisito original (Adicionar Compra,
  Receber Conta, Editar Cliente, Excluir Conta, Histórico, Fechar) — os 3
  primeiros ainda mostram apenas um aviso de "em construção" até suas
  respectivas etapas.
- **Editar Cliente**: reaproveita o mesmo componente de lista dinâmica do
  cadastro, pré-preenchido. Nomes alternativos/telefones são substituídos;
  compradores removidos são apenas inativados (nunca apagados), para não
  quebrar o vínculo com compras futuras.
- **Excluir Conta**: exclusão lógica com confirmação — cliente some das
  buscas, mas nada é apagado do banco.

## Etapa 2 — Login + Gestão de Usuários (novidade)

- Tela de login (PySide6), com validação de campos, tecla Enter para
  confirmar e mensagens de erro claras.
- `auth_service`: hash de senha com Argon2 (não guardamos senha em texto
  puro), verificação de credenciais. Login/senha incorretos **não** geram
  entrada no log de erros (é fluxo normal); apenas falhas técnicas (ex.:
  banco fora do ar) são logadas.
- Janela principal (`MainWindow`) exibida após o login, mostrando o nome e
  perfil do usuário logado, com as abas do sistema já estruturadas (ainda
  como placeholders — cada uma será implementada em sua própria etapa). As
  abas **Backup** e **Histórico e Relatórios** só aparecem para
  Administradores, conforme definido na análise de requisitos.
- Botão **Sair**, que encerra a sessão.
- Script `app/scripts/criar_usuario_admin.py` para criar o primeiro
  usuário administrador pelo terminal (necessário apenas para o primeiro
  acesso — depois disso, novos usuários são criados pela própria tela).
- **Tela "Usuários"** (aba visível só para Administrador): listar, criar,
  editar (nome/perfil), redefinir senha e inativar/reativar usuários.
  Toda alteração gera uma entrada em `historico_alteracoes`. Um
  Administrador não consegue inativar a própria conta.

### Criar o primeiro usuário e testar o login

Depois de configurar o `.env` e aplicar a migração inicial (etapa 1):

```bash
python -m app.scripts.criar_usuario_admin
```

Em seguida, rode a aplicação:

```bash
python -m app.main
```

A tela de login deve abrir; entre com o login/senha criados no passo
anterior para acessar a janela principal.

## O que foi implementado na etapa 1

- Estrutura de pastas completa do projeto (`app/config`, `database`,
  `models`, `repositories`, `services`, `controllers`, `views`, `utils`,
  `backups`, `logs`).
- Configuração via variáveis de ambiente (`.env`), sem dados sensíveis no
  código-fonte.
- Log de erros em arquivo (`app/logs/erros.log`), com data, hora, usuário,
  mensagem e stacktrace.
- Conexão com PostgreSQL via SQLAlchemy 2.0 + psycopg 3, com
  `session_scope()` garantindo commit/rollback automáticos por transação.
- Todos os modelos de dados (`Cliente`, `NomeAlternativo`, `Telefone`,
  `Comprador`, `Compra`, `Pagamento`, `PagamentoCompra`, `Usuario`,
  `HistoricoAlteracao`, `LogErro`), com UUID como chave primária, exclusão
  lógica (`ativo`), timestamps de auditoria e colunas normalizadas e
  indexadas para busca (nome principal, nomes alternativos, telefones).
- Setup do Alembic pronto para gerar e aplicar migrações.

## Como rodar

### 1. Pré-requisitos

- Python 3.13 instalado.
- Um servidor PostgreSQL acessível pela rede (pode ser o mesmo computador,
  para testes).

### 2. Instalar dependências

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar o banco

```bash
cp .env.example .env
```

Edite o `.env` com os dados reais do servidor PostgreSQL da rede local
(`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`). Crie o banco
vazio no PostgreSQL antes (ex.: `CREATE DATABASE fiado_db;`).

### 4. Gerar e aplicar a migração inicial

Como as tabelas ainda não existem no banco, gere a primeira migração e
aplique-a:

```bash
alembic revision --autogenerate -m "estrutura inicial"
alembic upgrade head
```

> Isso precisa ser rodado com o `.env` já configurado e o servidor
> PostgreSQL acessível — não foi possível gerar essa migração aqui porque
> este ambiente não tem acesso à sua rede/servidor.

### 5. Criar o primeiro usuário e rodar a aplicação

```bash
python -m app.scripts.criar_usuario_admin
python -m app.main
```

Se a conexão falhar, verifique o `.env` e consulte `app/logs/erros.log`
para detalhes.

## Próximas etapas (aguardando aprovação de cada uma)

1. ~~Sistema de login~~ ✅ concluído nesta entrega.
2. Cadastro de cliente (view + controller + service + repository).
3. Busca de cliente (com debounce, ranking e ficha do cliente).
4. Adicionar compra — inclui `app/utils/date_utils.py` com os modos "dia
   atual" / "dia anterior" (configuração global, editável na tela de
   configurações, mas a data sempre pode ser alterada manualmente em cada
   lançamento).
5. Receber conta (lógica FIFO + geração de "Resto").
6. Backup automático/manual e restauração.
7. Histórico de alterações e relatórios (saldo em aberto, exportação).
8. Tela de configurações (conexão, pasta de backup, modo de data padrão,
   tema).
