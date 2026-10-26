import os
import threading
import time
from datetime import datetime, timedelta

import requests


BASE = (
    "https://www.ana.gov.br/"
    "hidrowebservice/EstacoesTelemetricas"
)

URL_AUTH = BASE + "/OAUth/v1"
URL_SERIE = (
    BASE
    + "/HidroinfoanaSerieTelemetricaAdotada/v1"
)

ESTACOES_TESTE = {
    "Santa Tereza": "86472600",
    "Linha Jose Julio": "86472000",
}

_TOKEN = None
_TOKEN_CRIADO_EM = 0.0
_TOKEN_LOCK = threading.Lock()
TOKEN_REUSO_SEGUNDOS = 50 * 60

TIMEOUT = (8, 20)


def _log_seguro(log, mensagem):
    try:
        log(mensagem)
    except Exception:
        pass


def _numero(valor):

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    texto = texto.replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return None


def _data_hora(valor):

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    formatos = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]

    for formato in formatos:

        try:
            return datetime.strptime(
                texto,
                formato,
            )
        except Exception:
            pass

    return None


def obter_token(
    log=print,
    forcar=False,
):

    global _TOKEN
    global _TOKEN_CRIADO_EM

    agora = time.monotonic()

    if (
        not forcar
        and _TOKEN
        and (
            agora
            - _TOKEN_CRIADO_EM
        ) < TOKEN_REUSO_SEGUNDOS
    ):
        return _TOKEN

    with _TOKEN_LOCK:

        agora = time.monotonic()

        if (
            not forcar
            and _TOKEN
            and (
                agora
                - _TOKEN_CRIADO_EM
            ) < TOKEN_REUSO_SEGUNDOS
        ):
            return _TOKEN

        usuario = os.getenv(
            "ANA_API_USUARIO"
        )

        senha = os.getenv(
            "ANA_API_SENHA"
        )

        if not usuario or not senha:
            raise RuntimeError(
                "Credenciais da nova API ANA "
                "ausentes no ambiente."
            )

        resposta = requests.get(
            URL_AUTH,
            headers={
                "Identificador": usuario,
                "Senha": senha,
                "User-Agent":
                    "Monitor-Taquari-V3/1.0",
            },
            timeout=TIMEOUT,
        )

        resposta.raise_for_status()

        payload = resposta.json()

        items = (
            payload.get("items")
            or {}
        )

        if isinstance(items, list):
            item = (
                items[0]
                if items
                else {}
            )
        elif isinstance(items, dict):
            item = items
        else:
            item = {}

        token = (
            item.get(
                "tokenautenticacao"
            )
            or item.get(
                "Tokenautenticacao"
            )
            or item.get(
                "tokenAutenticacao"
            )
        )

        if not token:
            raise RuntimeError(
                "Token da nova API ANA "
                "nao localizado na resposta."
            )

        _TOKEN = token
        _TOKEN_CRIADO_EM = (
            time.monotonic()
        )

        _log_seguro(
            log,
            "ANA NOVA: token renovado com sucesso."
        )

        return _TOKEN


def _consultar_serie(
    codigo,
    token,
):

    resposta = requests.get(
        URL_SERIE,
        params={
            "Código da Estação":
                int(codigo),
            "Tipo Filtro Data":
                "DATA_LEITURA",
            "Data de Busca (yyyy-MM-dd)":
                datetime.now().strftime(
                    "%Y-%m-%d"
                ),
            "Range Intervalo de busca":
                "DIAS_30",
        },
        headers={
            "Authorization":
                "Bearer " + token,
            "User-Agent":
                "Monitor-Taquari-V3/1.0",
        },
        timeout=TIMEOUT,
    )

    return resposta


def buscar_estacao(
    nome,
    codigo,
    log=print,
    dias=2,
):

    token = obter_token(
        log=log
    )

    resposta = _consultar_serie(
        codigo,
        token,
    )

    # Token pode ter expirado antes do cache local.
    if resposta.status_code in (
        401,
        403,
    ):

        token = obter_token(
            log=log,
            forcar=True,
        )

        resposta = _consultar_serie(
            codigo,
            token,
        )

    resposta.raise_for_status()

    payload = resposta.json()

    registros_api = (
        payload.get("items")
        or []
    )

    if not isinstance(
        registros_api,
        list,
    ):
        raise RuntimeError(
            "Formato inesperado em items "
            "da nova API ANA."
        )

    limite = (
        datetime.now()
        - timedelta(
            days=max(
                1,
                int(dias),
            )
        )
    )

    registros = []

    for item in registros_api:

        if not isinstance(
            item,
            dict,
        ):
            continue

        dt = _data_hora(
            item.get(
                "Data_Hora_Medicao"
            )
            or item.get(
                "Data_Atualizacao"
            )
        )

        if dt is None:
            continue

        if dt < limite:
            continue

        cota_cm = _numero(
            item.get(
                "Cota_Adotada"
            )
        )

        if cota_cm is None:
            continue

        registros.append(
            {
                "estacao": nome,
                "codigo": str(codigo),
                "data_hora": dt,
                "nivel_m":
                    cota_cm / 100.0,
                "vazao": _numero(
                    item.get(
                        "Vazao_Adotada"
                    )
                ),
                "chuva": _numero(
                    item.get(
                        "Chuva_Adotada"
                    )
                ),
                "fonte_ana":
                    "HIDROWEBSERVICE",
            }
        )

    unicos = {}

    for registro in registros:

        chave = (
            registro["estacao"],
            registro["data_hora"],
        )

        unicos[chave] = registro

    saida = sorted(
        unicos.values(),
        key=lambda x:
            x["data_hora"],
    )

    if not saida:
        raise RuntimeError(
            "Nova API ANA retornou "
            "zero leituras validas para "
            + str(nome)
            + "."
        )

    ultimo = saida[-1]

    _log_seguro(
        log,
        (
            "ANA NOVA "
            + str(nome)
            + ": "
            + f'{ultimo["nivel_m"]:.2f} m '
            + "| "
            + ultimo["data_hora"].strftime(
                "%d/%m/%Y %H:%M"
            )
            + " | "
            + str(len(saida))
            + " leituras recentes"
        )
    )

    return saida


def testar_ana_nova_render(
    log=print,
):

    resultado = {
        "ok": True,
        "estacoes": {},
    }

    _log_seguro(
        log,
        "iniciando teste isolado de autenticacao."
    )

    try:

        token = obter_token(
            log=log,
            forcar=True,
        )

        if not token:
            raise RuntimeError(
                "Token nao obtido."
            )

        _log_seguro(
            log,
            "autenticacao HTTP 200"
        )

        _log_seguro(
            log,
            "autenticacao OK; token recebido e ocultado."
        )

    except Exception as exc:

        _log_seguro(
            log,
            "falha de autenticacao: "
            + type(exc).__name__
            + ": "
            + str(exc)
        )

        return {
            "ok": False,
            "erro": "autenticacao",
        }

    for nome, codigo in (
        ESTACOES_TESTE.items()
    ):

        try:

            resposta = _consultar_serie(
                codigo,
                token,
            )

            _log_seguro(
                log,
                nome
                + ": HTTP "
                + str(
                    resposta.status_code
                )
            )

            resposta.raise_for_status()

            payload = resposta.json()

            itens = (
                payload.get("items")
                or []
            )

            if not isinstance(
                itens,
                list,
            ):
                raise RuntimeError(
                    "items nao e lista"
                )

            _log_seguro(
                log,
                nome
                + ": registros="
                + str(len(itens))
            )

            ultimo = (
                itens[-1]
                if itens
                else {}
            )

            resumo = {
                "ok": True,
                "registros":
                    len(itens),
            }

            if isinstance(
                ultimo,
                dict,
            ):

                resumo[
                    "ultimo"
                ] = {
                    "data":
                        ultimo.get(
                            "Data_Hora_Medicao"
                        ),
                    "cota_cm":
                        ultimo.get(
                            "Cota_Adotada"
                        ),
                    "chuva_mm":
                        ultimo.get(
                            "Chuva_Adotada"
                        ),
                    "vazao_m3s":
                        ultimo.get(
                            "Vazao_Adotada"
                        ),
                    "qc_cota":
                        ultimo.get(
                            "Cota_Adotada_Status"
                        ),
                }

                _log_seguro(
                    log,
                    nome
                    + ": ultimo="
                    + str(
                        resumo["ultimo"]
                    )
                )

            resultado[
                "estacoes"
            ][nome] = resumo

        except Exception as exc:

            resultado["ok"] = False

            resultado[
                "estacoes"
            ][nome] = {
                "ok": False,
                "erro":
                    type(exc).__name__
                    + ": "
                    + str(exc),
            }

            _log_seguro(
                log,
                nome
                + ": falha: "
                + type(exc).__name__
                + ": "
                + str(exc)
            )

    resultado[
        "testado_em"
    ] = datetime.now().isoformat(
        timespec="seconds"
    )

    _log_seguro(
        log,
        "teste isolado concluido."
    )

    return resultado
