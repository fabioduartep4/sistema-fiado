"""Serviço de relatórios, histórico e painel inicial.

Reúne consultas administrativas: os três históricos da aba "Histórico"
(Vendas, Recebimentos e Alterações — auditoria genérica, com uma
descrição legível montada a partir do registro bruto de cada ação, ver
``_descrever_acao``), log de erros do sistema, relatório de clientes com
saldo em aberto (com exportação para CSV), as vendas de hoje (e dos
últimos 7 dias) e o painel de início (maior valor gasto, mais contas
lançadas, evolução mensal e total em aberto geral).

Todas as funções exigem perfil Administrador, na mesma linha dos demais
serviços administrativos (usuários, backup, configurações).
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.database.connection import session_scope
from app.models.usuario import PerfilUsuario
from app.repositories import (
    cliente_repository,
    historico_repository,
    log_erro_repository,
    pagamento_repository,
    relatorio_repository,
    usuario_repository,
)
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError
from app.utils.error_handler import tratar_erros

_ROTULOS_PERFIL = {
    PerfilUsuario.ADMINISTRADOR: "Administrador",
    PerfilUsuario.FUNCIONARIO: "Funcionário",
}


@dataclass(frozen=True)
class HistoricoResumo:
    """Uma entrada do histórico de alterações, para exibição.

    ``descricao`` já vem pronta para exibir (ex.: 'Editou o cliente:
    "João" → "João Silva".') — ver :func:`_descrever_acao`.
    """

    data_hora: datetime
    descricao: str
    usuario_nome: str


@dataclass(frozen=True)
class HistoricoFinanceiroResumo:
    """Uma entrada do histórico de Vendas ou de Recebimentos, para exibição.

    ``tipo`` ("Venda"/"Recebimento") existe pra quando as duas listas são
    combinadas numa tabela só (aba "Histórico" > "Vendas e Recebimentos",
    ou "Movimentações Recentes" no Início) — cada função que monta uma
    lista já sabe o próprio tipo, não precisa vir do banco.

    ``estornado`` só é usado pelo histórico de Recebimentos — um
    pagamento estornado continua aparecendo (o dinheiro foi recebido
    naquele dia), só marcado para deixar claro que foi desfeito depois.
    Nunca é True vindo do histórico de Vendas (compra não tem estorno).
    """

    data_hora: datetime
    cliente_nome: str
    valor: Decimal
    usuario_nome: str
    tipo: str
    estornado: bool = False


@dataclass(frozen=True)
class LogErroResumo:
    """Uma entrada do log de erros, para exibição."""

    data_hora: datetime
    usuario: str
    erro: str
    stacktrace: Optional[str]


@dataclass(frozen=True)
class SaldoClienteResumo:
    """Saldo em aberto de um cliente, para o relatório."""

    id: str
    id_visivel: int
    nome_principal: str
    total_em_aberto: Decimal


@dataclass(frozen=True)
class SaldoAtrasoResumo:
    """Saldo em aberto "atrasado" (compras em aberto há mais de N dias) de um cliente.

    ``total_em_atraso`` soma só as compras que passam do limite de dias;
    ``total_em_aberto`` é a situação completa da conta (atrasado ou não).
    """

    id: str
    id_visivel: int
    nome_principal: str
    telefone: Optional[str]
    total_em_atraso: Decimal
    total_em_aberto: Decimal
    dias_desde_a_compra_mais_antiga: int


@dataclass(frozen=True)
class ClienteAcimaDoLimiteResumo:
    """Cliente com saldo em aberto maior que o limite de fiado definido para ele."""

    id: str
    id_visivel: int
    nome_principal: str
    telefone: Optional[str]
    limite_fiado: Decimal
    total_em_aberto: Decimal
    excesso: Decimal


def _exigir_administrador(usuario_logado: UsuarioAutenticado) -> None:
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem acessar histórico e relatórios.")


def _extrair_campo(valor_empacotado: Optional[str], chave: str) -> Optional[str]:
    """Extrai o valor de uma chave de uma string empacotada tipo ``"a=1, b=2"``.

    Formato usado nos campos ``valor_antigo``/``valor_novo`` do histórico
    de alterações desde o início do projeto — nunca estruturado, sempre
    texto livre (ver docstring de :class:`app.models.historico_alteracao.HistoricoAlteracao`).
    Retorna ``None`` se a string for vazia ou não tiver essa chave.
    """
    if not valor_empacotado:
        return None
    for parte in valor_empacotado.split(", "):
        chave_encontrada, _, valor_encontrado = parte.partition("=")
        if chave_encontrada.strip() == chave:
            return valor_encontrado.strip()
    return None


def _descrever_acao(
    session: Session,
    entidade: str,
    entidade_id: uuid.UUID,
    acao: str,
    valor_antigo: Optional[str],
    valor_novo: Optional[str],
) -> str:
    """Traduz uma entrada bruta do histórico de alterações numa frase legível.

    Prioriza os valores já capturados em ``valor_antigo``/``valor_novo``
    (refletem o estado exato no momento da ação); quando a ação não
    guarda nada ali (ex.: exclusão lógica, redefinição de senha), busca o
    nome atual do registro relacionado — sempre possível, mesmo se
    inativo desde então, porque este sistema nunca apaga registros de
    verdade (exclusão lógica).

    Qualquer combinação de entidade/ação ainda não mapeada aqui (ex.: uma
    nova ação adicionada no futuro) cai no texto genérico do final, em
    vez de quebrar a tela.
    """
    if entidade == "Cliente":
        if acao == "criacao":
            nome = _extrair_campo(valor_novo, "nome_principal") or "?"
            return f'Cadastrou o cliente "{nome}".'
        if acao == "criacao_via_xml":
            nome = _extrair_campo(valor_novo, "nome_principal") or "?"
            return f'Cadastrou o cliente "{nome}" (via importação de XML).'
        if acao == "edicao":
            antigo = _extrair_campo(valor_antigo, "nome_principal")
            novo = _extrair_campo(valor_novo, "nome_principal")
            if antigo and novo and antigo != novo:
                return f'Editou o cliente: "{antigo}" → "{novo}".'
            return f'Editou o cliente "{novo or antigo or "?"}".'
        if acao == "exclusao_logica":
            cliente = cliente_repository.buscar_por_id(session, entidade_id)
            nome = cliente.nome_principal if cliente else "?"
            return f'Excluiu a conta do cliente "{nome}".'
        if acao == "confirmacao_xml":
            cliente = cliente_repository.buscar_por_id(session, entidade_id)
            nome = cliente.nome_principal if cliente else "?"
            return f'Confirmou o cadastro do cliente "{nome}" (criado via XML).'
        if acao == "mesclagem":
            nome_duplicado = _extrair_campo(valor_antigo, "nome_principal") or "?"
            id_principal = _extrair_campo(valor_novo, "mesclado_em")
            nome_principal = "?"
            if id_principal:
                principal = cliente_repository.buscar_por_id(session, uuid.UUID(id_principal))
                if principal is not None:
                    nome_principal = principal.nome_principal
            return f'Mesclou o cliente "{nome_duplicado}" com "{nome_principal}".'

    if entidade == "Usuario":
        usuario_alvo = usuario_repository.buscar_por_id(session, entidade_id)
        nome = usuario_alvo.nome if usuario_alvo else "?"
        if acao == "criacao":
            return f'Criou o usuário "{nome}".'
        if acao == "edicao":
            perfil_antigo = _extrair_campo(valor_antigo, "perfil")
            perfil_novo = _extrair_campo(valor_novo, "perfil")
            if perfil_antigo and perfil_novo and perfil_antigo != perfil_novo:
                rotulo_antigo = _ROTULOS_PERFIL.get(PerfilUsuario(perfil_antigo), perfil_antigo)
                rotulo_novo = _ROTULOS_PERFIL.get(PerfilUsuario(perfil_novo), perfil_novo)
                return f'Editou o usuário "{nome}" (perfil: {rotulo_antigo} → {rotulo_novo}).'
            return f'Editou o usuário "{nome}".'
        if acao == "redefinicao_senha":
            return f'Redefiniu a senha do usuário "{nome}".'
        if acao == "reativacao":
            return f'Reativou o usuário "{nome}".'
        if acao == "exclusao_logica":
            return f'Inativou o usuário "{nome}".'

    if entidade == "Pagamento" and acao == "estorno":
        valor = _extrair_campo(valor_antigo, "valor_pago") or "?"
        pagamento = pagamento_repository.buscar_por_id(session, entidade_id)
        nome_cliente = "?"
        if pagamento is not None:
            cliente = cliente_repository.buscar_por_id(session, pagamento.cliente_id)
            if cliente is not None:
                nome_cliente = cliente.nome_principal
        return f'Estornou um recebimento de R$ {valor} do cliente "{nome_cliente}".'

    return f"{acao.replace('_', ' ').capitalize()} ({entidade})."


@tratar_erros
def listar_historico(
    usuario_logado: UsuarioAutenticado, entidade: Optional[str] = None, limite: int = 200
) -> list[HistoricoResumo]:
    """Lista o histórico de alterações do sistema (aba "Histórico" > "Alterações").

    Não inclui lançamento de Compra/Pagamento (ver
    :func:`listar_historico_vendas`/:func:`listar_historico_recebimentos`,
    cada um com sua própria aba) nem login/logout — ver
    ``app.repositories.historico_repository.listar``.

    Args:
        usuario_logado: Usuário autenticado que está consultando.
        entidade: Filtro opcional por entidade (ex.: "Cliente").
        limite: Número máximo de registros retornados.

    Returns:
        Lista de :class:`HistoricoResumo`, mais recente primeiro.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    with session_scope() as session:
        registros = historico_repository.listar(session, entidade, limite)
        return [
            HistoricoResumo(
                data_hora=r.data_hora,
                descricao=_descrever_acao(
                    session, r.entidade, r.entidade_id, r.acao, r.valor_antigo, r.valor_novo
                ),
                usuario_nome=r.usuario.nome,
            )
            for r in registros
        ]


@tratar_erros
def listar_historico_vendas(
    usuario_logado: UsuarioAutenticado,
    limite: int = 200,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    cliente_nome: Optional[str] = None,
) -> list[HistoricoFinanceiroResumo]:
    """Lista as compras lançadas no sistema (aba "Histórico" > "Vendas e Recebimentos").

    Args:
        usuario_logado: Usuário autenticado que está consultando.
        limite: Número máximo de registros retornados.
        data_inicio: Filtro opcional — só a partir desta data.
        data_fim: Filtro opcional — só até esta data.
        cliente_nome: Filtro opcional por nome do cliente (contém).

    Returns:
        Lista de :class:`HistoricoFinanceiroResumo` (``tipo="Venda"``),
        mais recente primeiro (``estornado`` sempre False aqui — compra
        não tem estorno).

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    with session_scope() as session:
        registros = relatorio_repository.listar_historico_vendas(
            session, limite, data_inicio, data_fim, cliente_nome
        )
        return [
            HistoricoFinanceiroResumo(
                data_hora=data_hora,
                cliente_nome=cliente_nome_registro,
                valor=Decimal(valor),
                usuario_nome=usuario_nome,
                tipo="Venda",
            )
            for data_hora, cliente_nome_registro, valor, usuario_nome in registros
        ]


@tratar_erros
def listar_historico_recebimentos(
    usuario_logado: UsuarioAutenticado,
    limite: int = 200,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    cliente_nome: Optional[str] = None,
) -> list[HistoricoFinanceiroResumo]:
    """Lista os pagamentos recebidos no sistema (aba "Histórico" > "Vendas e Recebimentos").

    Inclui pagamentos já estornados (``estornado=True``) — o dinheiro foi
    recebido naquele dia, então continua aparecendo aqui, só marcado.

    Args:
        usuario_logado: Usuário autenticado que está consultando.
        limite: Número máximo de registros retornados.
        data_inicio: Filtro opcional — só a partir desta data.
        data_fim: Filtro opcional — só até esta data.
        cliente_nome: Filtro opcional por nome do cliente (contém).

    Returns:
        Lista de :class:`HistoricoFinanceiroResumo` (``tipo="Recebimento"``),
        mais recente primeiro.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    with session_scope() as session:
        registros = relatorio_repository.listar_historico_recebimentos(
            session, limite, data_inicio, data_fim, cliente_nome
        )
        return [
            HistoricoFinanceiroResumo(
                data_hora=data_hora,
                cliente_nome=cliente_nome_registro,
                valor=Decimal(valor),
                usuario_nome=usuario_nome,
                tipo="Recebimento",
                estornado=not ativo,
            )
            for data_hora, cliente_nome_registro, valor, usuario_nome, ativo in registros
        ]


def listar_movimentacoes(
    usuario_logado: UsuarioAutenticado,
    limite: int = 200,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    cliente_nome: Optional[str] = None,
    tipo: Optional[str] = None,
) -> list[HistoricoFinanceiroResumo]:
    """Combina Vendas + Recebimentos numa lista só, mais recente primeiro.

    Usado tanto pela aba "Histórico" > "Vendas e Recebimentos" (com os
    filtros preenchidos pelo usuário) quanto pela seção "Movimentações
    Recentes" do Início (sem filtro, só ``limite`` menor) — mesma lógica
    de combinar+ordenar, sem duplicar isso em cada view. Não tem
    ``@tratar_erros`` próprio: as duas funções que chama já são
    decoradas e já checam permissão.

    Args:
        usuario_logado: Usuário autenticado que está consultando.
        limite: Número máximo de registros retornados (aplicado depois de
            combinar — cada consulta individual já busca até ``limite``
            registros do próprio tipo antes de cortar).
        data_inicio: Filtro opcional — só a partir desta data.
        data_fim: Filtro opcional — só até esta data.
        cliente_nome: Filtro opcional por nome do cliente (contém).
        tipo: ``"Venda"`` ou ``"Recebimento"`` pra listar só um tipo;
            ``None`` (padrão) traz os dois combinados.

    Returns:
        Lista de :class:`HistoricoFinanceiroResumo`, mais recente primeiro.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    itens: list[HistoricoFinanceiroResumo] = []
    if tipo != "Recebimento":
        itens.extend(
            listar_historico_vendas(usuario_logado, limite, data_inicio, data_fim, cliente_nome)
        )
    if tipo != "Venda":
        itens.extend(
            listar_historico_recebimentos(usuario_logado, limite, data_inicio, data_fim, cliente_nome)
        )
    itens.sort(key=lambda item: item.data_hora, reverse=True)
    return itens[:limite]


@tratar_erros
def listar_log_erros(usuario_logado: UsuarioAutenticado, limite: int = 200) -> list[LogErroResumo]:
    """Lista os erros registrados pelo sistema.

    Args:
        usuario_logado: Usuário autenticado que está consultando.
        limite: Número máximo de registros retornados.

    Returns:
        Lista de :class:`LogErroResumo`, mais recente primeiro.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    with session_scope() as session:
        registros = log_erro_repository.listar(session, limite)
        return [
            LogErroResumo(
                data_hora=r.data_hora, usuario=r.usuario, erro=r.erro, stacktrace=r.stacktrace
            )
            for r in registros
        ]


@tratar_erros
def listar_saldos_em_aberto(usuario_logado: UsuarioAutenticado) -> list[SaldoClienteResumo]:
    """Lista os clientes com saldo em aberto (relatório).

    Args:
        usuario_logado: Usuário autenticado que está consultando.

    Returns:
        Lista de :class:`SaldoClienteResumo`, ordenada por nome principal.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    with session_scope() as session:
        linhas = relatorio_repository.listar_saldos_em_aberto(session)
        return [
            SaldoClienteResumo(
                id=str(cliente.id),
                id_visivel=cliente.id_visivel,
                nome_principal=cliente.nome_principal,
                total_em_aberto=Decimal(total),
            )
            for cliente, total in linhas
        ]


@tratar_erros
def listar_saldos_em_atraso(
    usuario_logado: UsuarioAutenticado, dias_atraso: int = 30
) -> list[SaldoAtrasoResumo]:
    """Lista clientes com saldo "em atraso" (compras em aberto há mais de N dias).

    Usado para o envio de lembretes de cobrança. Como o fiado não tem uma
    data de vencimento própria, a data da compra é usada como referência —
    quanto mais antiga uma compra ainda em aberto, mais atrasada ela conta.

    Args:
        usuario_logado: Usuário autenticado que está consultando.
        dias_atraso: Quantidade de dias, a partir da data da compra, para
            considerá-la em atraso.

    Returns:
        Lista de :class:`SaldoAtrasoResumo`, da maior para a menor soma.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    hoje = date.today()
    data_limite = hoje - timedelta(days=dias_atraso)

    with session_scope() as session:
        linhas = relatorio_repository.listar_saldos_em_atraso(session, data_limite)
        resultado = []
        for cliente, total_em_atraso, total_em_aberto, data_mais_antiga in linhas:
            telefone = cliente.telefones[0].numero if cliente.telefones else None
            resultado.append(
                SaldoAtrasoResumo(
                    id=str(cliente.id),
                    id_visivel=cliente.id_visivel,
                    nome_principal=cliente.nome_principal,
                    telefone=telefone,
                    total_em_atraso=Decimal(total_em_atraso),
                    total_em_aberto=Decimal(total_em_aberto),
                    dias_desde_a_compra_mais_antiga=(hoje - data_mais_antiga).days,
                )
            )
        return resultado


@tratar_erros
def listar_clientes_acima_do_limite(
    usuario_logado: UsuarioAutenticado,
) -> list[ClienteAcimaDoLimiteResumo]:
    """Lista clientes com saldo em aberto acima do limite de fiado definido para eles.

    Só considera clientes com um limite configurado (ver
    ``app.models.cliente.Cliente.limite_fiado``) — quem não tem limite
    definido nunca aparece aqui. Usado para destacar na tela de Início
    quem já passou do combinado, com o botão de enviar lembrete.

    Args:
        usuario_logado: Usuário autenticado que está consultando.

    Returns:
        Lista de :class:`ClienteAcimaDoLimiteResumo`, do maior excesso
        para o menor.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)

    with session_scope() as session:
        linhas = relatorio_repository.listar_clientes_acima_do_limite(session)
        resultado = []
        for cliente, total in linhas:
            telefone = cliente.telefones[0].numero if cliente.telefones else None
            total_em_aberto = Decimal(total)
            resultado.append(
                ClienteAcimaDoLimiteResumo(
                    id=str(cliente.id),
                    id_visivel=cliente.id_visivel,
                    nome_principal=cliente.nome_principal,
                    telefone=telefone,
                    limite_fiado=cliente.limite_fiado,
                    total_em_aberto=total_em_aberto,
                    excesso=total_em_aberto - cliente.limite_fiado,
                )
            )
        return resultado


@tratar_erros
def exportar_saldos_em_aberto_csv(usuario_logado: UsuarioAutenticado, caminho_arquivo: str) -> None:
    """Exporta o relatório de saldo em aberto para um arquivo CSV.

    O arquivo usa ``;`` como separador e codificação UTF-8 com BOM, para
    abrir corretamente (acentos incluídos) no Excel.

    Args:
        usuario_logado: Usuário autenticado que está exportando.
        caminho_arquivo: Caminho completo do arquivo ``.csv`` a ser criado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    saldos = listar_saldos_em_aberto(usuario_logado)

    with open(caminho_arquivo, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["Código", "Cliente", "Total em Aberto (R$)"])
        for saldo in saldos:
            escritor.writerow(
                [saldo.id_visivel, saldo.nome_principal, f"{saldo.total_em_aberto:.2f}"]
            )


@tratar_erros
def exportar_saldos_em_aberto_xlsx(usuario_logado: UsuarioAutenticado, caminho_arquivo: str) -> None:
    """Exporta o relatório de saldo em aberto para uma planilha Excel (``.xlsx``) formatada.

    Diferente da exportação em CSV, a planilha já sai com cabeçalho em
    negrito, largura de coluna ajustada, valores em formato moeda e uma
    linha de total ao final.

    Args:
        usuario_logado: Usuário autenticado que está exportando.
        caminho_arquivo: Caminho completo do arquivo ``.xlsx`` a ser criado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    saldos = listar_saldos_em_aberto(usuario_logado)

    pasta_trabalho = Workbook()
    planilha = pasta_trabalho.active
    planilha.title = "Saldo em Aberto"

    cabecalhos = ["Código", "Cliente", "Total em Aberto (R$)"]
    planilha.append(cabecalhos)
    for coluna, _ in enumerate(cabecalhos, start=1):
        celula = planilha.cell(row=1, column=coluna)
        celula.font = Font(bold=True)
        celula.alignment = Alignment(horizontal="center")

    for saldo in saldos:
        planilha.append([saldo.id_visivel, saldo.nome_principal, float(saldo.total_em_aberto)])

    linha_total = planilha.max_row + 1
    planilha.cell(row=linha_total, column=1, value="Total")
    planilha.cell(row=linha_total, column=1).font = Font(bold=True)
    celula_total = planilha.cell(
        row=linha_total, column=3, value=float(sum((s.total_em_aberto for s in saldos), Decimal("0")))
    )
    celula_total.font = Font(bold=True)

    for linha in range(2, linha_total + 1):
        planilha.cell(row=linha, column=3).number_format = '"R$" #,##0.00'

    larguras = [10, 40, 20]
    for coluna, largura in enumerate(larguras, start=1):
        planilha.column_dimensions[get_column_letter(coluna)].width = largura

    planilha.freeze_panes = "A2"
    pasta_trabalho.save(caminho_arquivo)


@dataclass(frozen=True)
class PontoVendaDiaria:
    """Um ponto da série de vendas diárias (últimos N dias)."""

    dia: str  # "dd/mm"
    total: Decimal


@dataclass(frozen=True)
class VendasHojeResumo:
    """Dados da seção "Vendas de Hoje" da tela de Início — situação do dia
    atual, sem filtro de período (não faz sentido escolher um "período"
    para "hoje").

    Attributes:
        total_vendido_hoje: Soma de tudo que foi vendido no fiado hoje.
        quantidade_vendida_hoje: Quantidade de compras lançadas hoje.
        vendas_ultimos_7_dias: Total vendido por dia, últimos 7 dias
            (janela fixa, incluindo hoje).
    """

    total_vendido_hoje: Decimal
    quantidade_vendida_hoje: int
    vendas_ultimos_7_dias: list[PontoVendaDiaria]


@tratar_erros
def obter_vendas_hoje(usuario_logado: UsuarioAutenticado) -> VendasHojeResumo:
    """Monta os dados da seção "Vendas de Hoje" — sempre o dia atual e os
    últimos 7 dias, sem período selecionável.

    Args:
        usuario_logado: Usuário autenticado que está consultando.

    Returns:
        Um :class:`VendasHojeResumo`.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem ver as vendas de hoje.")

    hoje = date.today()
    with session_scope() as session:
        total_hoje, quantidade_hoje = relatorio_repository.calcular_total_vendido_no_dia(session, hoje)
        vendas_diarias = relatorio_repository.listar_vendas_ultimos_dias(session, dias=7)
        return VendasHojeResumo(
            total_vendido_hoje=total_hoje,
            quantidade_vendida_hoje=quantidade_hoje,
            vendas_ultimos_7_dias=[
                PontoVendaDiaria(dia=dia.strftime("%d/%m"), total=total) for dia, total in vendas_diarias
            ],
        )


@dataclass(frozen=True)
class ClienteValorResumo:
    """Um cliente e um valor associado (gasto ou saldo em aberto), para gráficos."""

    nome_principal: str
    valor: Decimal


@dataclass(frozen=True)
class ClienteContagemResumo:
    """Um cliente e uma quantidade associada (nº de contas lançadas), para gráficos."""

    nome_principal: str
    quantidade: int


@dataclass(frozen=True)
class PontoEvolucaoMensal:
    """Um ponto da série de evolução mensal de vendas."""

    mes: str  # "AAAA-MM"
    total: Decimal


@dataclass(frozen=True)
class PainelInicio:
    """Dados do painel de Início (dashboard) que dependem de um período.

    Separado de :class:`PainelSaldos` porque nem tudo que já esteve nessa
    tela depende de período — "Total em aberto", "Evolução de Vendas" e
    "Clientes com Maior Saldo em Aberto" são a situação atual (ou uma
    janela fixa de 6 meses, no caso da evolução), não algo filtrável por
    data. Essas três foram para a aba "Saldos" (ver :func:`obter_painel_saldos`);
    aqui ficou só o que realmente muda conforme o período selecionado.
    """

    periodo_inicio: date
    periodo_fim: date
    maior_valor_gasto: list[ClienteValorResumo]
    mais_contas_lancadas: list[ClienteContagemResumo]


@tratar_erros
def obter_painel_inicio(
    usuario_logado: UsuarioAutenticado,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
) -> PainelInicio:
    """Monta os dados do painel de Início que dependem do período informado.

    Args:
        usuario_logado: Usuário autenticado que está consultando.
        data_inicio: Início do período. Se omitido, usa o primeiro dia do
            mês atual.
        data_fim: Fim do período. Se omitido, usa a data de hoje.

    Returns:
        Um :class:`PainelInicio` com os indicadores do período.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem ver o painel de início.")

    hoje = date.today()
    if data_inicio is None:
        data_inicio = hoje.replace(day=1)
    if data_fim is None:
        data_fim = hoje

    with session_scope() as session:
        maior_valor = relatorio_repository.listar_maior_valor_gasto(session, data_inicio, data_fim)
        mais_contas = relatorio_repository.listar_mais_contas_lancadas(session, data_inicio, data_fim)

        return PainelInicio(
            periodo_inicio=data_inicio,
            periodo_fim=data_fim,
            maior_valor_gasto=[
                ClienteValorResumo(nome_principal=cliente.nome_principal, valor=Decimal(valor))
                for cliente, valor in maior_valor
            ],
            mais_contas_lancadas=[
                ClienteContagemResumo(nome_principal=cliente.nome_principal, quantidade=int(quantidade))
                for cliente, quantidade in mais_contas
            ],
        )


@dataclass(frozen=True)
class PainelSaldos:
    """Dados da aba "Saldos" — situação atual das contas, sem filtro de período.

    Attributes:
        evolucao_mensal: Total vendido por mês, últimos 6 meses (janela
            fixa, não é afetada por nenhum período selecionável).
        total_em_aberto_geral: Soma de tudo que está em aberto no negócio,
            agora.
        maiores_saldos_em_aberto: Os 10 clientes com maior saldo em
            aberto, agora.
    """

    evolucao_mensal: list[PontoEvolucaoMensal]
    total_em_aberto_geral: Decimal
    maiores_saldos_em_aberto: list[ClienteValorResumo]


@tratar_erros
def obter_painel_saldos(usuario_logado: UsuarioAutenticado) -> PainelSaldos:
    """Monta os dados da aba "Saldos" — sempre a situação atual, sem período.

    Args:
        usuario_logado: Usuário autenticado que está consultando.

    Returns:
        Um :class:`PainelSaldos`.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem ver os saldos do negócio.")

    with session_scope() as session:
        evolucao = relatorio_repository.listar_evolucao_mensal(session, meses=6)
        total_aberto_geral = relatorio_repository.calcular_total_em_aberto_geral(session)
        saldos = relatorio_repository.listar_saldos_em_aberto(session)

        maiores_saldos = sorted(
            (
                ClienteValorResumo(nome_principal=cliente.nome_principal, valor=Decimal(total))
                for cliente, total in saldos
            ),
            key=lambda item: item.valor,
            reverse=True,
        )[:10]

        return PainelSaldos(
            evolucao_mensal=[PontoEvolucaoMensal(mes=mes, total=total) for mes, total in evolucao],
            total_em_aberto_geral=total_aberto_geral,
            maiores_saldos_em_aberto=maiores_saldos,
        )
