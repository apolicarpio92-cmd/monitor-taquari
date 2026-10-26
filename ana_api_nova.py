import os
from datetime import datetime

import requests


BASE = (
    "https://www.ana.gov.br/"
    "hidrowebservice/EstacoesTelemetricas"
)

ESTACOES_TESTE = {
    "Santa Tereza": "86472600",
    "Linha Jose Julio": "86472000",
}


def _log_seguro(log, mensagem):
    try:
        log(mensagem)
    except Exception:
        pass


def testar_ana_nova_render(log=print):

    usuario = os.getenv("ANA_API_USUARIO")
    senha = os.getenv("ANA_API_SENHA")

    if not usuario or not senha:
        _log_seguro(
            log,
            "credenciais ausentes no ambiente."
        )
        return {
            "ok": False,
            "erro": "credenciais_ausentes",
        }

    _log_seguro(
        log,
        "iniciando teste isolado de autenticacao."
    )

    try:
        resposta_auth = requests.get(
            BASE + "/OAUth/v1",
            headers={
                "Identificador": usuario,
                "Senha": senha,
                "User-Agent": "Monitor-Taquari-V3/1.0",
            },
            timeout=(8, 20),
        )
    except Exception as exc:
        _log_seguro(
            log,
            "erro de conexao na autenticacao: "
            + type(exc).__name__
            + ": "
            + str(exc)
        )
        return {
            "ok": False,
            "erro": "conexao_auth",
        }

    _log_seguro(
        log,
        "autenticacao HTTP "
        + str(resposta_auth.status_code)
    )

    if resposta_auth.status_code != 200:
        _log_seguro(
            log,
            "autenticacao recusada pela ANA."
        )
        return {
            "ok": False,
            "erro": "http_auth",
            "http": resposta_auth.status_code,
        }

    try:
        payload_auth = resposta_auth.json()
    except Exception:
        _log_seguro(
            log,
            "resposta de autenticacao nao e JSON."
        )
        return {
            "ok": False,
            "erro": "json_auth",
        }

    items_auth = payload_auth.get("items") or {}

    if isinstance(items_auth, list):
        item_token = (
            items_auth[0]
            if items_auth
            else {}
        )
    elif isinstance(items_auth, dict):
        item_token = items_auth
    else:
        item_token = {}

    token = (
        item_token.get("tokenautenticacao")
        or item_token.get("Tokenautenticacao")
        or item_token.get("tokenAutenticacao")
    )

    if not token:
        _log_seguro(
            log,
            "autenticacao respondeu, mas o token "
            "nao foi localizado."
        )
        return {
            "ok": False,
            "erro": "token_ausente",
        }

    _log_seguro(
        log,
        "autenticacao OK; token recebido e ocultado."
    )

    url_serie = (
        BASE
        + "/HidroinfoanaSerieTelemetricaAdotada/v1"
    )

    resultado = {
        "ok": True,
        "estacoes": {},
    }

    for nome, codigo in ESTACOES_TESTE.items():

        try:
            resposta = requests.get(
                url_serie,
                params={
                    "Código da Estação": int(codigo),
                    "Tipo Filtro Data": "DATA_LEITURA",
                    "Data de Busca (yyyy-MM-dd)": (
                        datetime.now().strftime(
                            "%Y-%m-%d"
                        )
                    ),
                    "Range Intervalo de busca": "DIAS_30",
                },
                headers={
                    "Authorization": "Bearer " + token,
                    "User-Agent": "Monitor-Taquari-V3/1.0",
                },
                timeout=(8, 20),
            )
        except Exception as exc:
            _log_seguro(
                log,
                nome
                + ": erro de conexao: "
                + type(exc).__name__
                + ": "
                + str(exc)
            )
            resultado["estacoes"][nome] = {
                "ok": False,
                "erro": "conexao",
            }
            continue

        _log_seguro(
            log,
            nome
            + ": HTTP "
            + str(resposta.status_code)
        )

        if resposta.status_code != 200:

            detalhe = None

            try:
                erro_json = resposta.json()

                if isinstance(erro_json, dict):
                    detalhe = {
                        "status": erro_json.get("status"),
                        "code": erro_json.get("code"),
                        "message": erro_json.get("message"),
                    }

            except Exception:
                detalhe = (
                    resposta.text[:500]
                    if resposta.text
                    else None
                )

            _log_seguro(
                log,
                nome
                + ": erro HTTP "
                + str(resposta.status_code)
                + " detalhe="
                + str(detalhe)
            )

            resultado["estacoes"][nome] = {
                "ok": False,
                "http": resposta.status_code,
                "detalhe": detalhe,
            }

            continue

        try:
            payload = resposta.json()
        except Exception:
            _log_seguro(
                log,
                nome + ": resposta nao e JSON."
            )
            resultado["estacoes"][nome] = {
                "ok": False,
                "erro": "json",
            }
            continue

        registros = payload.get("items") or []

        if not isinstance(registros, list):
            _log_seguro(
                log,
                nome + ": formato de items inesperado."
            )
            resultado["estacoes"][nome] = {
                "ok": False,
                "erro": "formato_items",
            }
            continue

        _log_seguro(
            log,
            nome
            + ": registros="
            + str(len(registros))
        )

        resumo = {
            "ok": True,
            "registros": len(registros),
        }

        if registros:
            ultimo = registros[-1]

            if isinstance(ultimo, dict):
                resumo["ultimo"] = {
                    "data": (
                        ultimo.get("Data_Hora_Medicao")
                        or ultimo.get("Data_Atualizacao")
                    ),
                    "cota_cm": ultimo.get("Cota_Adotada"),
                    "chuva_mm": ultimo.get("Chuva_Adotada"),
                    "vazao_m3s": ultimo.get("Vazao_Adotada"),
                    "qc_cota": ultimo.get(
                        "Cota_Adotada_Status"
                    ),
                }

                _log_seguro(
                    log,
                    nome
                    + ": ultimo="
                    + str(resumo["ultimo"])
                )

        resultado["estacoes"][nome] = resumo

    resultado["testado_em"] = datetime.now().isoformat(
        timespec="seconds"
    )

    _log_seguro(
        log,
        "teste isolado concluido."
    )

    return resultado
