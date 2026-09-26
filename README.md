# Sistema de Gestão de Fiado

Programa desktop (Windows) para controlar as contas de fiado do mercado:
cadastro de clientes, compras, pagamentos, saldos, lembretes por WhatsApp
e importação automática das vendas a prazo a partir dos XMLs de NF-e.
Vários computadores da loja usam o mesmo banco PostgreSQL pela rede.

Feito em Python com PySide6 (interface) e PostgreSQL (dados).

---

## Como funciona

### Perfis de usuário

- **Administrador**: acesso a tudo.
- **Funcionário**: só a tela **Clientes** e o botão **+ Novo Lançamento**.
  Em Clientes ele busca pelo nome e só vê o saldo ao abrir a ficha do
  cliente.

### Telas

| Tela | O que faz |
|---|---|
| **Início** | Resumo do dia: total em aberto, vendas de hoje, clientes, quem está acima do limite, clientes com maior atraso, movimentações recentes e gráficos. |
| **Clientes** | Busca e lista de clientes com saldo, limite e situação. Filtros: Com saldo, Em atraso, Acima do limite. Botão **+ Novo Cliente**. Duplo clique abre a ficha. |
| **Ficha do Cliente** | Saldo, limite e disponível; histórico de compras e pagamentos. Botões: + Nova Compra, Receber Pagamento, Enviar Lembrete, Extrato, Ver Produtos (compras vindas de XML), Editar Cliente e Excluir Conta. |
| **Saldos** | Todos os clientes com saldo em aberto, com busca e exportação para CSV/Excel. |
| **Histórico** | Vendas e recebimentos (com filtro de período, cliente e tipo), alterações feitas no sistema e log de erros. |
| **Backups** | Pasta de backup, backup manual e restauração. |
| **Configurações** | Modo de data padrão, tema claro/escuro, pasta dos XMLs, importação de XML, clientes duplicados e usuários. |

O botão **+ Novo Lançamento**, no topo de todas as telas, abre direto
**Compra** ou **Pagamento**.

### Regras de negócio

- **Compra**: lança um valor na conta do cliente. A data sugerida é o
  **dia anterior** ou o **dia atual** (escolhido em Configurações), e
  sempre pode ser alterada.
- **Pagamento**: quita as compras **mais antigas primeiro**. Se o valor
  pago acabar no meio de uma compra, ela é quitada e o que faltou vira uma
  nova compra chamada **"Resto"**. Um pagamento pode ser estornado com
  duplo clique nele, na ficha do cliente.
- **Limite de fiado**: opcional, por cliente. Quem passa do limite aparece
  em destaque no Início e em Clientes.
- **Atraso**: cliente com compra em aberto há mais de 30 dias (o número de
  dias pode ser alterado nas telas Início e Clientes).
- **Exclusão**: nada é apagado de verdade; clientes e usuários excluídos
  só ficam inativos, e toda alteração fica registrada no Histórico.

### Importação de XML de NF-e

Em **Configurações**, escolha a pasta onde o emissor de notas grava os
XMLs. Ao abrir o sistema (ou em **Importar XMLs Agora**), ele procura notas
de **venda a prazo pagas com Crédito Loja** que ainda não foram importadas
e pergunta a qual cliente cada uma pertence (ou cria um cliente novo,
marcado como "pendente de confirmação"). Só a parte da nota paga no fiado
vira compra. No Histórico, essas vendas aparecem com a data e a hora de
emissão da nota. Os produtos da nota podem ser vistos pela ficha do
cliente.

### Lembrete por WhatsApp

Na ficha de qualquer cliente com saldo, **Enviar Lembrete** abre o
WhatsApp com a mensagem pronta para revisar e enviar:

- **Acima do limite** → avisa que passou do limite combinado.
- **Em atraso** → avisa do atraso, cita o último pagamento e o total da conta.
- **Em dia** → só informa o total da conta.

### Impressão

Feita para impressora térmica de **80 mm** (ex.: Elgin i9), sempre com
pré-visualização antes:

- **Extrato**: nome, telefone, compras em aberto (data e valor) e total.
- **Comprovante de pagamento**: oferecido ao registrar um pagamento.

### Backup

- **Automático**: uma vez por dia, verificado ao abrir o sistema e enquanto
  ele estiver aberto.
- **Manual** e **restauração**: na tela Backups.
- Usa `pg_dump` e `psql`, que precisam estar instalados (vêm com o
  PostgreSQL) e no PATH do computador.

### Atalhos de teclado

| Atalho | Ação |
|---|---|
| `Ctrl+N` | Novo cliente |
| `Ctrl+F` | Buscar cliente |
| `Ctrl+Q` | Sair |

---

## Como rodar

### Requisitos

- Windows com **Python 3.13**.
- Um servidor **PostgreSQL** acessível pela rede (pode ser o próprio
  computador, para testes).

### 1. Instalar as dependências

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar a conexão com o banco

Copie `.env.example` para `.env` e preencha com os dados do servidor:

```
DB_HOST=192.168.0.10
DB_PORT=5432
DB_NAME=fiado_db
DB_USER=fiado_user
DB_PASSWORD=sua_senha
BACKUP_DIR=./app/backups
LOG_DIR=./app/logs
```

Se o servidor PostgreSQL for novo, rode `preparar_banco.bat` uma vez: ele
lê o `.env`, pede a senha do usuário `postgres` e cria o usuário, o banco e
o schema que faltarem. As tabelas são criadas e atualizadas sozinhas quando
o sistema abre.

### 3. Criar o primeiro usuário administrador

```bash
python -m app.scripts.criar_usuario_admin
```

Os próximos usuários são criados pelo próprio sistema, em Configurações.

### 4. Abrir o sistema

```bash
python -m app.main
```

Se não conectar, confira o `.env` e o arquivo `app/logs/erros.log`.

---

## Instalar nos computadores da loja (.exe)

Assim os computadores não precisam ter Python.

1. Num computador Windows com Python 3.13, dê duplo clique em
   **`build_exe.bat`**. Ele instala tudo e gera a pasta
   `dist\SistemaFiado`.
2. Copie a pasta **`dist\SistemaFiado` inteira** para cada computador.
3. Em cada um, coloque um `.env` dentro dessa pasta (os dados costumam ser
   os mesmos em todos, já que apontam para o mesmo servidor).
4. Servidor novo: rode `preparar_banco.bat` e depois
   `CriarUsuarioAdmin.exe` para criar o primeiro login. Isso é feito uma
   vez por servidor, não por computador.
5. Abra o **`SistemaFiado.exe`**.

Se o Windows bloquear o `CriarUsuarioAdmin.exe`, rode
`criar_admin_emergencia.sql` no banco (pelo `psql` ou pgAdmin). Ele cria o
usuário `admin` com senha `admin123`; troque a senha logo depois, em
Configurações > Usuários.

---

## Testes

```bash
pip install -r requirements-test.txt
pytest
```

Por padrão rodam só os testes que não usam o banco. Para rodar também os
testes de integração, aponte o `.env` para um **banco de testes** (eles
criam e excluem dados de verdade) e rode:

```powershell
$env:RODAR_TESTES_INTEGRACAO="1"; pytest
```
