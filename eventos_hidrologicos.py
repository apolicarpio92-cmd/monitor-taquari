from __future__ import annotations

import csv
import statistics
from datetime import datetime, timedelta
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent

ARQ_TELEMETRIA = (
    BASE_DIR
    / "historico"
    / "telemetria_historico.csv"
)


# ============================================================
# CABECEIRAS / VACARIA
# ============================================================

LATITUDE_CABECEIRAS = -28.50
LONGITUDE_CABECEIRAS = -50.95

URL_HISTORICO_METEO = (
    "https://historical-forecast-api.open-meteo.com"
    "/v1/forecast"
)

TIMEZONE = "America/Sao_Paulo"

CACHE_MINUTOS = 30

_CACHE = {
    "momento": None,
    "dados": None,
}


# ============================================================
# PARAMETROS EXPERIMENTAIS
# ============================================================

CHUVA_MINIMA_HORA = 0.2

# Até 3h sem chuva ainda pertence ao mesmo bloco meteorológico.
INTERVALO_SECO_MAX_H = 3

CHUVA_MINIMA_EVENTO_MM = 5.0

# Depois do fim da chuva ainda acompanhamos a resposta do rio.
JANELA_RESPOSTA_H = 36

SUBIDA_MINIMA_RESPOSTA_M = 0.10
MARGEM_SUSTENTADA_M = 0.08

# Se o rio já subiu pelo menos este valor nas 3h anteriores
# ao início da chuva, não tratamos aquela chuva como início
# independente de uma resposta hidrológica.
SUBIDA_PREVIA_M = 0.08

# Chuvas diferentes que chegam exatamente ao mesmo pico
# podem fazer parte da mesma onda hidrológica.
MAX_GAP_MESMO_PICO_H = 24

# Pequenas oscilações não devem virar "evento de cheia".
ELEVACAO_MINIMA_EVENTO_M = 0.20


# ============================================================
# CONVERSOES
# ============================================================

def para_float(valor):

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    # CSV atual usa decimal brasileiro.
    if "," in texto:
        texto = (
            texto
            .replace(".", "")
            .replace(",", ".")
        )

    try:
        return float(texto)

    except Exception:
        return None


def para_data(valor):

    if not valor:
        return None

    texto = str(valor).strip()

    formatos = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    )

    for formato in formatos:

        try:
            return datetime.strptime(
                texto,
                formato,
            )

        except Exception:
            pass

    try:
        return datetime.fromisoformat(
            texto
        )

    except Exception:
        return None


# ============================================================
# TELEMETRIA
# ============================================================

def carregar_telemetria():

    if not ARQ_TELEMETRIA.exists():
        return []

    registros = []

    try:

        with ARQ_TELEMETRIA.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as arquivo:

            leitor = csv.DictReader(
                arquivo,
                delimiter=";",
            )

            for linha in leitor:

                dt = para_data(
                    linha.get("data_hora")
                )

                nivel = para_float(
                    linha.get("nivel_m")
                )

                if (
                    dt is None
                    or nivel is None
                ):
                    continue

                registros.append(
                    {
                        "estacao": (
                            linha.get(
                                "estacao",
                                "",
                            )
                            or ""
                        ).strip(),

                        "codigo": (
                            linha.get(
                                "codigo",
                                "",
                            )
                            or ""
                        ).strip(),

                        "data_hora": dt,
                        "nivel": nivel,
                    }
                )

    except Exception as e:

        print(
            "[EVENTOS] Erro telemetria:",
            e,
            flush=True,
        )

        return []

    registros.sort(
        key=lambda x: x["data_hora"]
    )

    return registros


def serie_estacao(
    registros,
    codigo,
):

    return [
        r
        for r in registros
        if r["codigo"] == codigo
    ]


# ============================================================
# CHUVA HISTORICA
# ============================================================

def buscar_chuva_cabeceiras(
    inicio,
    fim,
):

    params = {
        "latitude":
            LATITUDE_CABECEIRAS,

        "longitude":
            LONGITUDE_CABECEIRAS,

        "timezone":
            TIMEZONE,

        "start_date":
            inicio.strftime(
                "%Y-%m-%d"
            ),

        "end_date":
            fim.strftime(
                "%Y-%m-%d"
            ),

        "hourly":
            "precipitation",
    }

    resposta = requests.get(
        URL_HISTORICO_METEO,
        params=params,
        timeout=20,
    )

    resposta.raise_for_status()

    dados = resposta.json()

    hourly = dados.get(
        "hourly",
        {},
    )

    tempos = hourly.get(
        "time",
        [],
    )

    chuvas = hourly.get(
        "precipitation",
        [],
    )

    resultado = []

    for i, texto_data in enumerate(
        tempos
    ):

        try:

            dt = datetime.fromisoformat(
                texto_data
            )

            mm = float(
                chuvas[i]
                or 0
            )

        except Exception:
            continue

        resultado.append(
            {
                "data_hora": dt,
                "mm": mm,
            }
        )

    return resultado


# ============================================================
# EVENTOS METEOROLOGICOS
# ============================================================

def detectar_eventos_chuva(
    registros,
):

    molhados = [
        r
        for r in registros
        if r["mm"] >= CHUVA_MINIMA_HORA
    ]

    if not molhados:
        return []

    grupos = []
    grupo = [molhados[0]]

    for atual in molhados[1:]:

        anterior = grupo[-1]

        intervalo = (
            atual["data_hora"]
            - anterior["data_hora"]
        ).total_seconds() / 3600

        if intervalo <= INTERVALO_SECO_MAX_H:

            grupo.append(
                atual
            )

        else:

            grupos.append(
                grupo
            )

            grupo = [atual]

    grupos.append(
        grupo
    )

    eventos = []

    for grupo in grupos:

        inicio = grupo[0]["data_hora"]
        fim = grupo[-1]["data_hora"]

        chuva_evento = [
            r
            for r in registros
            if (
                inicio
                <= r["data_hora"]
                <= fim
            )
        ]

        total = sum(
            r["mm"]
            for r in chuva_evento
        )

        maxima = max(
            (
                r["mm"]
                for r in chuva_evento
            ),
            default=0,
        )

        if total < CHUVA_MINIMA_EVENTO_MM:
            continue

        eventos.append(
            {
                "inicio": inicio,
                "fim": fim,

                "chuva_mm":
                    round(
                        total,
                        1,
                    ),

                "max_mm_h":
                    round(
                        maxima,
                        1,
                    ),

                "chuvas_agrupadas":
                    1,
            }
        )

    return eventos


def classe_chuva(mm):

    if mm < 20:
        return "FRACA"

    if mm < 50:
        return "MODERADA"

    if mm < 100:
        return "FORTE"

    return "MUITO FORTE"


# ============================================================
# ANALISE DA RESPOSTA DO RIO
# ============================================================

def analisar_resposta(
    serie,
    evento,
):

    inicio = evento["inicio"]
    fim_evento = evento["fim"]

    limite = (
        fim_evento
        + timedelta(
            hours=JANELA_RESPOSTA_H
        )
    )

    base_inicio = (
        inicio
        - timedelta(
            hours=3
        )
    )

    base_registros = [
        r
        for r in serie
        if (
            base_inicio
            <= r["data_hora"]
            < inicio
        )
    ]

    if len(base_registros) < 3:

        return {
            "baseline": None,
            "tendencia_previa_m": None,
            "ja_estava_subindo": None,
            "resposta": None,
            "pico": None,
            "elevacao_pico_m": None,
        }

    baseline = statistics.median(
        [
            r["nivel"]
            for r in base_registros
        ]
    )

    primeiro_base = base_registros[0]["nivel"]
    ultimo_base = base_registros[-1]["nivel"]

    tendencia_previa = (
        ultimo_base
        - primeiro_base
    )

    ja_estava_subindo = (
        tendencia_previa
        >= SUBIDA_PREVIA_M
    )

    janela = [
        r
        for r in serie
        if (
            inicio
            <= r["data_hora"]
            <= limite
        )
    ]

    if not janela:

        return {
            "baseline":
                round(
                    baseline,
                    2,
                ),

            "tendencia_previa_m":
                round(
                    tendencia_previa,
                    2,
                ),

            "ja_estava_subindo":
                ja_estava_subindo,

            "resposta":
                None,

            "pico":
                None,

            "elevacao_pico_m":
                None,
        }

    # ========================================================
    # PRIMEIRA SUBIDA SUSTENTADA
    # ========================================================

    resposta = None

    limite_resposta = (
        baseline
        + SUBIDA_MINIMA_RESPOSTA_M
    )

    limite_sustentado = (
        baseline
        + MARGEM_SUSTENTADA_M
    )

    for i, registro in enumerate(
        janela
    ):

        if (
            registro["nivel"]
            < limite_resposta
        ):
            continue

        proximos = janela[
            i:i + 5
        ]

        sustentados = sum(
            1
            for p in proximos
            if (
                p["nivel"]
                >= limite_sustentado
            )
        )

        if sustentados >= 3:

            resposta = registro
            break

    pico = max(
        janela,
        key=lambda x: x["nivel"],
    )

    elevacao_pico = (
        pico["nivel"]
        - baseline
    )

    return {
        "baseline":
            round(
                baseline,
                2,
            ),

        "tendencia_previa_m":
            round(
                tendencia_previa,
                2,
            ),

        "ja_estava_subindo":
            ja_estava_subindo,

        "resposta":
            resposta,

        "pico":
            pico,

        "elevacao_pico_m":
            round(
                elevacao_pico,
                2,
            ),
    }


# ============================================================
# DURACOES
# ============================================================

def diferenca_minutos(
    inicio,
    fim,
):

    if (
        inicio is None
        or fim is None
    ):
        return None

    valor = (
        fim - inicio
    ).total_seconds() / 60

    if valor < 0:
        return None

    return int(
        round(valor)
    )


def resumo_tempos(
    valores,
):

    valores = sorted(
        [
            int(v)
            for v in valores
            if (
                v is not None
                and v >= 0
            )
        ]
    )

    if not valores:

        return {
            "quantidade": 0,
            "min": None,
            "mediana": None,
            "max": None,
        }

    return {
        "quantidade":
            len(valores),

        "min":
            min(valores),

        "mediana":
            int(
                round(
                    statistics.median(
                        valores
                    )
                )
            ),

        "max":
            max(valores),
    }


# ============================================================
# PRIMEIRA ANALISE DOS BLOCOS DE CHUVA
# ============================================================

def montar_evento_analisado(
    evento,
    santa,
    linha,
):

    resposta_santa = analisar_resposta(
        santa,
        evento,
    )

    resposta_linha = analisar_resposta(
        linha,
        evento,
    )

    return {
        **evento,

        "_resposta_santa":
            resposta_santa,

        "_resposta_linha":
            resposta_linha,
    }


# ============================================================
# AGRUPA CHUVAS QUE CONDUZEM AO MESMO PICO
# ============================================================

def consolidar_mesmo_pico(
    eventos,
    santa,
    linha,
):

    if not eventos:
        return []

    ordenados = sorted(
        eventos,
        key=lambda e: e["inicio"],
    )

    consolidados = []

    for atual in ordenados:

        pico_atual = (
            atual[
                "_resposta_santa"
            ].get(
                "pico"
            )
        )

        agrupado = False

        if (
            consolidados
            and pico_atual
        ):

            anterior = consolidados[-1]

            pico_anterior = (
                anterior[
                    "_resposta_santa"
                ].get(
                    "pico"
                )
            )

            if pico_anterior:

                mesmo_pico = (
                    pico_atual[
                        "data_hora"
                    ]
                    == pico_anterior[
                        "data_hora"
                    ]
                )

                gap_h = (
                    atual["inicio"]
                    - anterior["fim"]
                ).total_seconds() / 3600

                if (
                    mesmo_pico
                    and gap_h
                    <= MAX_GAP_MESMO_PICO_H
                ):

                    anterior[
                        "fim"
                    ] = max(
                        anterior["fim"],
                        atual["fim"],
                    )

                    anterior[
                        "chuva_mm"
                    ] = round(
                        anterior[
                            "chuva_mm"
                        ]
                        + atual[
                            "chuva_mm"
                        ],
                        1,
                    )

                    anterior[
                        "max_mm_h"
                    ] = max(
                        anterior[
                            "max_mm_h"
                        ],
                        atual[
                            "max_mm_h"
                        ],
                    )

                    anterior[
                        "chuvas_agrupadas"
                    ] = (
                        anterior.get(
                            "chuvas_agrupadas",
                            1,
                        )
                        + atual.get(
                            "chuvas_agrupadas",
                            1,
                        )
                    )

                    # Recalcula a resposta considerando
                    # o episódio completo.
                    anterior[
                        "_resposta_santa"
                    ] = analisar_resposta(
                        santa,
                        anterior,
                    )

                    anterior[
                        "_resposta_linha"
                    ] = analisar_resposta(
                        linha,
                        anterior,
                    )

                    agrupado = True

        if not agrupado:

            consolidados.append(
                dict(atual)
            )

    return consolidados


# ============================================================
# CLASSIFICACAO DO EVENTO
# ============================================================

def validar_evento(
    evento,
):

    santa = evento[
        "_resposta_santa"
    ]

    if santa.get(
        "baseline"
    ) is None:

        return (
            False,
            "Histórico insuficiente antes da chuva."
        )

    if santa.get(
        "ja_estava_subindo"
    ) is True:

        return (
            False,
            (
                "Santa Tereza já estava subindo "
                "antes do início deste episódio de chuva."
            )
        )

    if santa.get(
        "resposta"
    ) is None:

        return (
            False,
            "Não foi detectada uma subida sustentada posterior."
        )

    if santa.get(
        "pico"
    ) is None:

        return (
            False,
            "Não foi possível identificar o pico posterior."
        )

    elevacao = santa.get(
        "elevacao_pico_m"
    )

    if (
        elevacao is None
        or elevacao
        < ELEVACAO_MINIMA_EVENTO_M
    ):

        return (
            False,
            (
                "A oscilação observada foi pequena "
                "demais para aprendizado hidrológico."
            )
        )

    return (
        True,
        (
            "Rio estava estável antes da chuva "
            "e apresentou subida sustentada posterior."
        )
    )


# ============================================================
# CONVERTE EVENTO PARA JSON
# ============================================================

def serializar_evento(
    evento,
):

    rs = evento[
        "_resposta_santa"
    ]

    rl = evento[
        "_resposta_linha"
    ]

    inicio = evento[
        "inicio"
    ]

    inicio_santa = (
        rs["resposta"]["data_hora"]
        if rs.get("resposta")
        else None
    )

    pico_santa = (
        rs["pico"]["data_hora"]
        if rs.get("pico")
        else None
    )

    inicio_linha = (
        rl["resposta"]["data_hora"]
        if rl.get("resposta")
        else None
    )

    pico_linha = (
        rl["pico"]["data_hora"]
        if rl.get("pico")
        else None
    )

    valido, motivo = validar_evento(
        evento
    )

    tempo_resposta_santa = (
        diferenca_minutos(
            inicio,
            inicio_santa,
        )
    )

    tempo_pico_santa = (
        diferenca_minutos(
            inicio,
            pico_santa,
        )
    )

    tempo_resposta_linha = (
        diferenca_minutos(
            inicio,
            inicio_linha,
        )
    )

    linha_santa_pico = None

    if (
        pico_linha
        and pico_santa
    ):

        linha_santa_pico = (
            diferenca_minutos(
                pico_linha,
                pico_santa,
            )
        )

    return {
        "inicio":
            inicio.isoformat(
                timespec="minutes"
            ),

        "fim":
            evento[
                "fim"
            ].isoformat(
                timespec="minutes"
            ),

        "chuva_mm":
            evento[
                "chuva_mm"
            ],

        "max_mm_h":
            evento[
                "max_mm_h"
            ],

        "classe":
            classe_chuva(
                evento[
                    "chuva_mm"
                ]
            ),

        "chuvas_agrupadas":
            evento.get(
                "chuvas_agrupadas",
                1,
            ),

        "valido_aprendizado":
            valido,

        "motivo_validacao":
            motivo,

        "linha": {
            "baseline":
                rl.get(
                    "baseline"
                ),

            "tendencia_previa_m":
                rl.get(
                    "tendencia_previa_m"
                ),

            "ja_estava_subindo":
                rl.get(
                    "ja_estava_subindo"
                ),

            "resposta":
                (
                    inicio_linha.isoformat(
                        timespec="minutes"
                    )
                    if inicio_linha
                    else None
                ),

            "pico":
                (
                    pico_linha.isoformat(
                        timespec="minutes"
                    )
                    if pico_linha
                    else None
                ),

            "pico_nivel":
                (
                    round(
                        rl["pico"][
                            "nivel"
                        ],
                        2,
                    )
                    if rl.get("pico")
                    else None
                ),

            "tempo_resposta_min":
                tempo_resposta_linha,
        },

        "santa": {
            "baseline":
                rs.get(
                    "baseline"
                ),

            "tendencia_previa_m":
                rs.get(
                    "tendencia_previa_m"
                ),

            "ja_estava_subindo":
                rs.get(
                    "ja_estava_subindo"
                ),

            "resposta":
                (
                    inicio_santa.isoformat(
                        timespec="minutes"
                    )
                    if inicio_santa
                    else None
                ),

            "pico":
                (
                    pico_santa.isoformat(
                        timespec="minutes"
                    )
                    if pico_santa
                    else None
                ),

            "pico_nivel":
                (
                    round(
                        rs["pico"][
                            "nivel"
                        ],
                        2,
                    )
                    if rs.get("pico")
                    else None
                ),

            "elevacao_pico_m":
                rs.get(
                    "elevacao_pico_m"
                ),

            "tempo_resposta_min":
                tempo_resposta_santa,

            "tempo_pico_min":
                tempo_pico_santa,
        },

        "linha_santa_pico_min":
            linha_santa_pico,
    }


# ============================================================
# ANALISE COMPLETA
# ============================================================

def analisar_eventos_hidrologicos(
    forcar=False,
):

    agora = datetime.now()

    if (
        not forcar
        and _CACHE["dados"] is not None
        and _CACHE["momento"] is not None
        and (
            agora
            - _CACHE["momento"]
        ).total_seconds()
        < CACHE_MINUTOS * 60
    ):

        return _CACHE[
            "dados"
        ]

    telemetria = carregar_telemetria()

    if not telemetria:

        return {
            "ok": False,
            "erro": (
                "Histórico de telemetria "
                "ainda não disponível."
            ),
        }

    inicio_telemetria = min(
        r["data_hora"]
        for r in telemetria
    )

    fim_telemetria = max(
        r["data_hora"]
        for r in telemetria
    )

    inicio = max(
        inicio_telemetria,
        fim_telemetria
        - timedelta(
            days=30
        ),
    )

    try:

        chuva = buscar_chuva_cabeceiras(
            inicio,
            fim_telemetria,
        )

    except Exception as e:

        resultado = {
            "ok": False,
            "erro": (
                "Não foi possível consultar "
                "a chuva histórica das cabeceiras: "
                + str(e)
            ),
        }

        _CACHE["momento"] = agora
        _CACHE["dados"] = resultado

        return resultado

    eventos_chuva = detectar_eventos_chuva(
        chuva
    )

    santa = serie_estacao(
        telemetria,
        "86472600",
    )

    linha = serie_estacao(
        telemetria,
        "86472000",
    )

    preliminares = [
        montar_evento_analisado(
            evento,
            santa,
            linha,
        )
        for evento in eventos_chuva
    ]

    consolidados = consolidar_mesmo_pico(
        preliminares,
        santa,
        linha,
    )

    eventos = [
        serializar_evento(
            evento
        )
        for evento in consolidados
    ]

    eventos.sort(
        key=lambda x: x["inicio"],
        reverse=True,
    )

    validos = [
        e
        for e in eventos
        if e.get(
            "valido_aprendizado"
        )
    ]

    tempos_resposta = [
        e["santa"][
            "tempo_resposta_min"
        ]
        for e in validos
    ]

    tempos_pico = [
        e["santa"][
            "tempo_pico_min"
        ]
        for e in validos
    ]

    linha_santa = [
        e[
            "linha_santa_pico_min"
        ]
        for e in validos
    ]

    resultado = {
        "ok": True,

        "fonte_chuva":
            (
                "Estimativa meteorológica "
                "histórica — Open-Meteo"
            ),

        "periodo": {
            "inicio":
                inicio.isoformat(
                    timespec="minutes"
                ),

            "fim":
                fim_telemetria.isoformat(
                    timespec="minutes"
                ),
        },

        "eventos_encontrados":
            len(eventos),

        "eventos_analisados":
            len(eventos),

        "eventos_validos":
            len(validos),

        "eventos_informativos":
            (
                len(eventos)
                - len(validos)
            ),

        "resumo": {
            "chuva_resposta_santa":
                resumo_tempos(
                    tempos_resposta
                ),

            "chuva_pico_santa":
                resumo_tempos(
                    tempos_pico
                ),

            "linha_pico_santa_pico":
                resumo_tempos(
                    linha_santa
                ),
        },

        "eventos":
            eventos[:12],
    }

    _CACHE["momento"] = agora
    _CACHE["dados"] = resultado

    return resultado


# ============================================================
# HTML
# ============================================================

def gerar_html_eventos_hidrologicos():

    return r'''
<style>

.eventos-hidro {
    margin-top:18px;
    margin-bottom:18px;
    padding:20px;
    border-radius:16px;
    background:#151e23;
    border:1px solid #2b3941;
    color:#f4f7f8;
}

.eventos-titulo {
    color:#8fb8d0;
    font-size:15px;
    font-weight:800;
    letter-spacing:.04em;
}

.eventos-subtitulo {
    margin-top:4px;
    color:#819ba9;
    font-size:11px;
}

.eventos-contagem {
    display:flex;
    flex-wrap:wrap;
    gap:8px;
    margin-top:13px;
}

.eventos-contagem span {
    padding:6px 9px;
    border-radius:7px;
    background:#0c1418;
    border:1px solid #293a43;
    color:#91aab6;
    font-size:10px;
}

.eventos-contagem strong {
    color:#fff;
}

.eventos-resumo {
    display:grid;
    grid-template-columns:
        repeat(3,minmax(0,1fr));
    gap:10px;
    margin-top:13px;
}

.eventos-card {
    background:#0c1418;
    border:1px solid #293a43;
    border-radius:11px;
    padding:12px;
}

.eventos-card span {
    display:block;
    color:#7593a2;
    font-size:10px;
    margin-bottom:5px;
}

.eventos-card strong {
    display:block;
    color:#fff;
    font-size:18px;
}

.eventos-faixa {
    margin-top:5px;
    color:#7e9aa8;
    font-size:10px;
}

.eventos-lista {
    margin-top:15px;
}

.evento-item {
    padding:13px;
    margin-top:9px;
    border-radius:11px;
    background:#0e171c;
    border:1px solid #263740;
}

.evento-item-informativo {
    opacity:.78;
}

.evento-topo {
    display:flex;
    justify-content:space-between;
    gap:12px;
    align-items:center;
    flex-wrap:wrap;
}

.evento-data {
    color:#fff;
    font-size:13px;
    font-weight:700;
}

.evento-chuva {
    color:#9fc9de;
    font-size:12px;
    font-weight:700;
}

.evento-validacao {
    margin-top:8px;
    display:flex;
    align-items:center;
    flex-wrap:wrap;
    gap:7px;
}

.evento-badge {
    display:inline-block;
    padding:4px 7px;
    border-radius:6px;
    font-size:9px;
    font-weight:800;
}

.evento-valido {
    color:#a9dfc3;
    background:#10231b;
    border:1px solid #315943;
}

.evento-info {
    color:#c1ccd1;
    background:#182126;
    border:1px solid #39484f;
}

.evento-motivo {
    color:#718d9a;
    font-size:9px;
}

.evento-grid {
    display:grid;
    grid-template-columns:
        repeat(4,minmax(0,1fr));
    gap:8px;
    margin-top:10px;
}

.evento-dado {
    background:#091216;
    border-radius:8px;
    padding:8px;
}

.evento-dado span {
    display:block;
    color:#698895;
    font-size:9px;
    margin-bottom:4px;
}

.evento-dado strong {
    color:#fff;
    font-size:12px;
}

.eventos-nota {
    margin-top:12px;
    color:#66818e;
    font-size:9px;
    line-height:1.5;
}

.eventos-status {
    margin-top:15px;
    color:#a6bbc4;
    font-size:12px;
}

@media(max-width:900px) {

    .eventos-resumo {
        grid-template-columns:1fr;
    }

    .evento-grid {
        grid-template-columns:
            repeat(2,minmax(0,1fr));
    }
}

@media(max-width:520px) {

    .eventos-hidro {
        padding:14px;
    }

    .evento-grid {
        grid-template-columns:1fr;
    }
}

</style>

<section
    class="eventos-hidro"
    id="eventos-hidrologicos"
>

    <div class="eventos-titulo">
        TEMPO OBSERVADO —
        CABECEIRAS → SANTA TEREZA
    </div>

    <div class="eventos-subtitulo">
        Aprendizado por eventos de chuva
        e resposta posterior do rio
    </div>

    <div
        id="eventos-hidro-conteudo"
        class="eventos-status"
    >
        Analisando eventos históricos...
    </div>

</section>

<script>

(function () {

function duracao(
    minutos
) {

    if (
        minutos === null
        || minutos === undefined
    ) {
        return "-";
    }

    minutos =
        Math.round(
            Number(minutos)
        );

    const h =
        Math.floor(
            minutos / 60
        );

    const m =
        minutos % 60;

    if (
        h > 0
        && m > 0
    ) {
        return (
            h
            + "h"
            + String(m).padStart(
                2,
                "0"
            )
        );
    }

    if (h > 0) {
        return h + "h";
    }

    return m + " min";
}


function dataHora(
    valor
) {

    if (!valor) {
        return "-";
    }

    return new Date(
        valor
    ).toLocaleString(
        "pt-BR",
        {
            day:"2-digit",
            month:"2-digit",
            hour:"2-digit",
            minute:"2-digit"
        }
    );
}


function resumoCard(
    titulo,
    dados
) {

    if (
        !dados
        || !dados.quantidade
    ) {

        return `
        <div class="eventos-card">

            <span>
                ${titulo}
            </span>

            <strong>
                EM APRENDIZADO
            </strong>

            <div class="eventos-faixa">
                Ainda sem eventos válidos suficientes.
            </div>

        </div>
        `;
    }

    return `
    <div class="eventos-card">

        <span>
            ${titulo}
        </span>

        <strong>
            ${duracao(
                dados.mediana
            )}
        </strong>

        <div class="eventos-faixa">
            observado:
            ${duracao(dados.min)}
            a
            ${duracao(dados.max)}
            ·
            ${dados.quantidade}
            evento(s) válido(s)
        </div>

    </div>
    `;
}


async function carregarEventos() {

    const destino =
        document.getElementById(
            "eventos-hidro-conteudo"
        );

    if (!destino) {
        return;
    }

    try {

        const resposta =
            await fetch(
                "/api/eventos-hidrologicos",
                {
                    cache:"no-store"
                }
            );

        if (!resposta.ok) {

            throw new Error(
                "HTTP "
                + resposta.status
            );
        }

        const dados =
            await resposta.json();

        if (!dados.ok) {

            destino.innerHTML =
                `
                Não foi possível analisar
                os eventos neste momento.
                `;

            return;
        }

        const resumo =
            dados.resumo || {};

        let html =
            `
            <div class="eventos-contagem">

                <span>
                    Eventos encontrados:
                    <strong>
                        ${dados.eventos_encontrados || 0}
                    </strong>
                </span>

                <span>
                    Válidos para aprendizado:
                    <strong>
                        ${dados.eventos_validos || 0}
                    </strong>
                </span>

                <span>
                    Apenas informativos:
                    <strong>
                        ${dados.eventos_informativos || 0}
                    </strong>
                </span>

            </div>

            <div class="eventos-resumo">

                ${resumoCard(
                    "Chuva → início da subida em Santa Tereza",
                    resumo.chuva_resposta_santa
                )}

                ${resumoCard(
                    "Chuva → maior nível observado em Santa Tereza",
                    resumo.chuva_pico_santa
                )}

                ${resumoCard(
                    "Pico Linha José Júlio → pico Santa Tereza",
                    resumo.linha_pico_santa_pico
                )}

            </div>
            `;

        const eventos =
            dados.eventos || [];

        if (!eventos.length) {

            html +=
                `
                <div class="eventos-status">
                    Nenhum evento relevante encontrado
                    no histórico atual.
                </div>
                `;
        }

        else {

            html +=
                `
                <div class="eventos-lista">
                `;

            eventos.forEach(
                evento => {

                    const valido =
                        !!evento.valido_aprendizado;

                    const classeItem =
                        valido
                        ? ""
                        : " evento-item-informativo";

                    const classeBadge =
                        valido
                        ? "evento-valido"
                        : "evento-info";

                    const textoBadge =
                        valido
                        ? "✓ VÁLIDO PARA APRENDIZADO"
                        : "○ INFORMATIVO";

                    let agrupamento = "";

                    if (
                        Number(
                            evento.chuvas_agrupadas
                            || 1
                        ) > 1
                    ) {

                        agrupamento =
                            " · "
                            + evento.chuvas_agrupadas
                            + " blocos de chuva agrupados";
                    }

                    html +=
                        `
                        <div
                            class="
                                evento-item
                                ${classeItem}
                            "
                        >

                            <div class="evento-topo">

                                <div class="evento-data">
                                    Evento iniciado em
                                    ${dataHora(
                                        evento.inicio
                                    )}
                                </div>

                                <div class="evento-chuva">
                                    ${Number(
                                        evento.chuva_mm
                                    ).toLocaleString(
                                        "pt-BR",
                                        {
                                            minimumFractionDigits:1,
                                            maximumFractionDigits:1
                                        }
                                    )}
                                    mm
                                    ·
                                    ${evento.classe}
                                    ${agrupamento}
                                </div>

                            </div>

                            <div class="evento-validacao">

                                <span
                                    class="
                                        evento-badge
                                        ${classeBadge}
                                    "
                                >
                                    ${textoBadge}
                                </span>

                                <span class="evento-motivo">
                                    ${evento.motivo_validacao || ""}
                                </span>

                            </div>

                            <div class="evento-grid">

                                <div class="evento-dado">

                                    <span>
                                        Início da chuva
                                    </span>

                                    <strong>
                                        ${dataHora(
                                            evento.inicio
                                        )}
                                    </strong>

                                </div>

                                <div class="evento-dado">

                                    <span>
                                        Santa começou a responder
                                    </span>

                                    <strong>
                                        ${dataHora(
                                            evento.santa.resposta
                                        )}
                                    </strong>

                                </div>

                                <div class="evento-dado">

                                    <span>
                                        Chuva → resposta Santa
                                    </span>

                                    <strong>
                                        ${duracao(
                                            evento.santa
                                                .tempo_resposta_min
                                        )}
                                    </strong>

                                </div>

                                <div class="evento-dado">

                                    <span>
                                        Chuva → pico Santa
                                    </span>

                                    <strong>
                                        ${duracao(
                                            evento.santa
                                                .tempo_pico_min
                                        )}
                                    </strong>

                                </div>

                            </div>

                        </div>
                        `;
                }
            );

            html +=
                "</div>";
        }

        html +=
            `
            <div class="eventos-nota">
                As estatísticas do topo utilizam somente
                eventos classificados como válidos para aprendizado.
                Chuvas ocorridas enquanto o rio já estava subindo,
                eventos sem histórico anterior suficiente e
                duplicações do mesmo pico permanecem apenas como
                informação e não alteram a mediana.
                Chuva das cabeceiras:
                ${dados.fonte_chuva}.
                Análise experimental — não representa previsão
                ou alerta oficial.
            </div>
            `;

        destino.innerHTML =
            html;

    }

    catch (erro) {

        destino.innerHTML =
            `
            A análise de eventos está
            temporariamente indisponível.
            `;
    }
}


carregarEventos();

})();

</script>
'''


if __name__ == "__main__":

    import json

    resultado = (
        analisar_eventos_hidrologicos(
            forcar=True
        )
    )

    print(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2,
        )
    )
