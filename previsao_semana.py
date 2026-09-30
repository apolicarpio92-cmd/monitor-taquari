from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape

import requests


# ============================================================
# CONFIGURACAO
# ============================================================

URL = "https://api.open-meteo.com/v1/forecast"

TIMEZONE = "America/Sao_Paulo"

CACHE_SEGUNDOS = 3600


LOCAIS = {

    "santa_tereza": {
        "nome": "Santa Tereza - RS",
        "titulo": (
            "PREVISÃO METEOROLÓGICA "
            "— SANTA TEREZA — 7 DIAS"
        ),
        "subtitulo": (
            "Santa Tereza · foco em precipitação "
            "para acompanhamento hidrológico"
        ),
        "latitude": -29.1781,
        "longitude": -51.7322,
    },

    "cabeceiras": {
        "nome": "Cabeceiras / Vacaria - RS",
        "titulo": (
            "PREVISÃO METEOROLÓGICA "
            "— CABECEIRAS / VACARIA — 7 DIAS"
        ),
        "subtitulo": (
            "Cabeceiras do sistema Taquari-Antas · "
            "referência meteorológica em Vacaria"
        ),
        "latitude": -28.50,
        "longitude": -50.95,
    },
}


_CACHE = {}


# ============================================================
# TEMPO
# ============================================================

def descricao_tempo(codigo):

    mapa = {
        0: ("Céu limpo", "☀️"),
        1: ("Predomínio de sol", "🌤️"),
        2: ("Parcialmente nublado", "⛅"),
        3: ("Nublado", "☁️"),
        45: ("Nevoeiro", "🌫️"),
        48: ("Nevoeiro", "🌫️"),
        51: ("Garoa fraca", "🌦️"),
        53: ("Garoa", "🌦️"),
        55: ("Garoa intensa", "🌧️"),
        56: ("Garoa congelante", "🌧️"),
        57: ("Garoa congelante forte", "🌧️"),
        61: ("Chuva fraca", "🌦️"),
        63: ("Chuva moderada", "🌧️"),
        65: ("Chuva forte", "🌧️"),
        66: ("Chuva congelante", "🌧️"),
        67: ("Chuva congelante forte", "🌧️"),
        71: ("Neve fraca", "❄️"),
        73: ("Neve", "❄️"),
        75: ("Neve forte", "❄️"),
        77: ("Grãos de neve", "❄️"),
        80: ("Pancadas fracas", "🌦️"),
        81: ("Pancadas", "🌧️"),
        82: ("Pancadas fortes", "⛈️"),
        85: ("Pancadas de neve", "❄️"),
        86: ("Neve forte", "❄️"),
        95: ("Trovoadas", "⛈️"),
        96: ("Trovoadas com granizo", "⛈️"),
        99: ("Trovoadas fortes", "⛈️"),
    }

    try:
        codigo = int(codigo)
    except Exception:
        codigo = -1

    return mapa.get(
        codigo,
        ("Condição variável", "🌤️"),
    )


def nome_dia(dt):

    dias = [
        "SEG",
        "TER",
        "QUA",
        "QUI",
        "SEX",
        "SÁB",
        "DOM",
    ]

    return dias[dt.weekday()]


def numero(valor, casas=1):

    try:
        return round(
            float(valor),
            casas,
        )

    except Exception:
        return 0.0


# ============================================================
# COLETA
# ============================================================

URL_MET_NORWAY = (
    "https://api.met.no/weatherapi/"
    "locationforecast/2.0/compact"
)

FUSO_BRASIL = ZoneInfo(
    "America/Sao_Paulo"
)

_CACHE = {}

_CACHE_GERAL = {
    "em": None,
    "dados": {},
    "fonte": None,
    "ultimo_erro": None,
    "ultimo_erro_em": None,
}


# ============================================================
# HELPERS
# ============================================================

def _numero_seguro(
    valor,
    padrao=0.0,
):

    try:
        return float(
            valor
        )

    except Exception:
        return float(
            padrao
        )


def _cache_valido():

    momento = _CACHE_GERAL.get(
        "em"
    )

    dados = _CACHE_GERAL.get(
        "dados"
    )

    if (
        momento is None
        or not dados
    ):
        return False

    idade = (
        datetime.now()
        - momento
    ).total_seconds()

    return (
        idade
        < CACHE_SEGUNDOS
    )


def _resultado_cache(
    local,
):

    resultado = (
        _CACHE_GERAL
        .get(
            "dados",
            {},
        )
        .get(
            local
        )
    )

    if not resultado:
        return None

    copia = dict(
        resultado
    )

    copia["cache"] = True

    return copia


# ============================================================
# DESCRICAO MET NORWAY
# ============================================================

def _descricao_met(
    codigo,
):

    codigo = (
        str(
            codigo
            or ""
        )
        .lower()
        .strip()
    )

    mapa_exato = {
        "clearsky_day":
            ("Céu limpo", "☀️"),

        "clearsky_night":
            ("Céu limpo", "🌙"),

        "fair_day":
            ("Predomínio de sol", "🌤️"),

        "fair_night":
            ("Poucas nuvens", "🌙"),

        "partlycloudy_day":
            ("Parcialmente nublado", "⛅"),

        "partlycloudy_night":
            ("Parcialmente nublado", "☁️"),

        "cloudy":
            ("Nublado", "☁️"),

        "fog":
            ("Nevoeiro", "🌫️"),
    }

    if codigo in mapa_exato:

        return mapa_exato[
            codigo
        ]

    if "thunder" in codigo:

        if "rain" in codigo:
            return (
                "Trovoadas com chuva",
                "⛈️",
            )

        return (
            "Trovoadas",
            "⛈️",
        )

    if "heavyrain" in codigo:

        return (
            "Chuva forte",
            "🌧️",
        )

    if "rain" in codigo:

        return (
            "Chuva",
            "🌧️",
        )

    if "heavysleet" in codigo:

        return (
            "Precipitação intensa",
            "🌧️",
        )

    if "sleet" in codigo:

        return (
            "Chuva e gelo",
            "🌧️",
        )

    if "heavysnow" in codigo:

        return (
            "Neve forte",
            "❄️",
        )

    if "snow" in codigo:

        return (
            "Neve",
            "❄️",
        )

    return (
        "Condição variável",
        "🌤️",
    )


# ============================================================
# OPEN-METEO
# ============================================================

def _montar_openmeteo_local(
    local,
    dados,
    agora,
):

    cfg = LOCAIS[
        local
    ]

    hourly = dados.get(
        "hourly",
        {},
    )

    daily = dados.get(
        "daily",
        {},
    )

    horas = hourly.get(
        "time",
        [],
    )

    precipitacao_hora = hourly.get(
        "precipitation",
        [],
    )

    registros_horarios = []

    inicio_hora = agora.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    for indice, texto_data in enumerate(
        horas
    ):

        try:

            dt = datetime.fromisoformat(
                texto_data
            )

        except Exception:
            continue

        if dt < inicio_hora:
            continue

        chuva = 0.0

        if indice < len(
            precipitacao_hora
        ):

            chuva = _numero_seguro(
                precipitacao_hora[
                    indice
                ]
            )

        registros_horarios.append(
            (
                dt,
                chuva,
            )
        )

    limite_24 = (
        agora
        + timedelta(
            hours=24
        )
    )

    limite_72 = (
        agora
        + timedelta(
            hours=72
        )
    )

    chuva_24h = sum(
        chuva
        for dt, chuva
        in registros_horarios
        if dt <= limite_24
    )

    chuva_72h = sum(
        chuva
        for dt, chuva
        in registros_horarios
        if dt <= limite_72
    )

    datas = daily.get(
        "time",
        [],
    )

    codigos = daily.get(
        "weather_code",
        [],
    )

    maximas = daily.get(
        "temperature_2m_max",
        [],
    )

    minimas = daily.get(
        "temperature_2m_min",
        [],
    )

    chuvas = daily.get(
        "precipitation_sum",
        [],
    )

    probabilidades = daily.get(
        "precipitation_probability_max",
        [],
    )

    rajadas = daily.get(
        "wind_gusts_10m_max",
        [],
    )

    dias = []

    for i, data_texto in enumerate(
        datas
    ):

        try:

            dt = datetime.fromisoformat(
                data_texto
            )

        except Exception:
            continue

        codigo = (
            codigos[i]
            if i < len(
                codigos
            )
            else None
        )

        descricao, icone = (
            descricao_tempo(
                codigo
            )
        )

        dias.append(
            {
                "data":
                    data_texto,

                "dia_semana":
                    (
                        "HOJE"
                        if (
                            dt.date()
                            == agora.date()
                        )
                        else nome_dia(
                            dt
                        )
                    ),

                "data_curta":
                    dt.strftime(
                        "%d/%m"
                    ),

                "codigo":
                    codigo,

                "descricao":
                    descricao,

                "icone":
                    icone,

                "maxima":
                    numero(
                        maximas[i]
                        if i < len(
                            maximas
                        )
                        else 0
                    ),

                "minima":
                    numero(
                        minimas[i]
                        if i < len(
                            minimas
                        )
                        else 0
                    ),

                "chuva":
                    numero(
                        chuvas[i]
                        if i < len(
                            chuvas
                        )
                        else 0
                    ),

                "probabilidade":
                    int(
                        numero(
                            probabilidades[i]
                            if i < len(
                                probabilidades
                            )
                            else 0,
                            0,
                        )
                    ),

                "rajada":
                    numero(
                        rajadas[i]
                        if i < len(
                            rajadas
                        )
                        else 0
                    ),
            }
        )

    chuva_7d = sum(
        dia["chuva"]
        for dia in dias
    )

    mais_chuvoso = None

    if dias:

        mais_chuvoso = max(
            dias,
            key=lambda d:
                d["chuva"],
        )

    return {
        "ok": True,

        "chave_local":
            local,

        "local":
            cfg["nome"],

        "titulo":
            cfg["titulo"],

        "subtitulo":
            cfg["subtitulo"],

        "latitude":
            cfg["latitude"],

        "longitude":
            cfg["longitude"],

        "atualizado_em":
            agora.isoformat(
                timespec="minutes"
            ),

        "chuva_24h":
            round(
                chuva_24h,
                1,
            ),

        "chuva_72h":
            round(
                chuva_72h,
                1,
            ),

        "chuva_7d":
            round(
                chuva_7d,
                1,
            ),

        "mais_chuvoso":
            mais_chuvoso,

        "dias":
            dias,

        "fonte":
            "Open-Meteo",

        "cache":
            False,

        "fallback":
            False,
    }


def _buscar_openmeteo():

    agora = datetime.now()

    chaves = list(
        LOCAIS.keys()
    )

    latitudes = ",".join(
        str(
            LOCAIS[chave][
                "latitude"
            ]
        )
        for chave in chaves
    )

    longitudes = ",".join(
        str(
            LOCAIS[chave][
                "longitude"
            ]
        )
        for chave in chaves
    )

    params = {
        "latitude":
            latitudes,

        "longitude":
            longitudes,

        "timezone":
            TIMEZONE,

        "forecast_days":
            7,

        "hourly":
            ",".join(
                [
                    "precipitation",
                    "precipitation_probability",
                ]
            ),

        "daily":
            ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_gusts_10m_max",
                ]
            ),
    }

    resposta = requests.get(
        URL,
        params=params,
        timeout=20,
        headers={
            "User-Agent":
                "MonitorTaquari/1.0"
        },
    )

    resposta.raise_for_status()

    bruto = resposta.json()

    if isinstance(
        bruto,
        dict,
    ):

        lista = [
            bruto
        ]

    elif isinstance(
        bruto,
        list,
    ):

        lista = bruto

    else:

        raise RuntimeError(
            "Formato inesperado "
            "do Open-Meteo."
        )

    if len(lista) != len(
        chaves
    ):

        raise RuntimeError(
            "Open-Meteo retornou "
            "quantidade inesperada "
            "de localidades."
        )

    resultados = {}

    for chave, dados in zip(
        chaves,
        lista,
    ):

        resultados[
            chave
        ] = (
            _montar_openmeteo_local(
                chave,
                dados,
                agora,
            )
        )

    return resultados


# ============================================================
# MET NORWAY
# ============================================================

def _buscar_met_local(
    local,
):

    cfg = LOCAIS[
        local
    ]

    params = {
        "lat":
            round(
                float(
                    cfg[
                        "latitude"
                    ]
                ),
                4,
            ),

        "lon":
            round(
                float(
                    cfg[
                        "longitude"
                    ]
                ),
                4,
            ),
    }

    headers = {
        "User-Agent":
            (
                "MonitorTaquari/1.0 "
                "https://monitor-taquari.onrender.com"
            ),
    }

    resposta = requests.get(
        URL_MET_NORWAY,
        params=params,
        headers=headers,
        timeout=20,
    )

    resposta.raise_for_status()

    return resposta.json()


def _converter_data_met(
    texto,
):

    dt = datetime.fromisoformat(
        texto.replace(
            "Z",
            "+00:00",
        )
    )

    return dt.astimezone(
        FUSO_BRASIL
    )


def _precipitacao_periodo_met(
    dados_periodo,
):

    if not isinstance(
        dados_periodo,
        dict,
    ):
        return 0.0

    detalhes = dados_periodo.get(
        "details",
        {},
    )

    return _numero_seguro(
        detalhes.get(
            "precipitation_amount",
            0,
        )
    )


def _probabilidade_periodo_met(
    dados_periodo,
):

    if not isinstance(
        dados_periodo,
        dict,
    ):
        return 0.0

    detalhes = dados_periodo.get(
        "details",
        {},
    )

    return _numero_seguro(
        detalhes.get(
            "probability_of_precipitation",
            0,
        )
    )


def _montar_met_local(
    local,
    bruto,
):

    cfg = LOCAIS[
        local
    ]

    agora = datetime.now()

    serie = (
        bruto.get(
            "properties",
            {},
        )
        .get(
            "timeseries",
            []
        )
    )

    if not serie:

        raise RuntimeError(
            "MET Norway retornou "
            "serie meteorologica vazia."
        )

    pontos = []

    # --------------------------------------------------------
    # Converte a serie para horario local.
    #
    # A API pode passar de resolucao horaria
    # para intervalos maiores ao longo da previsao.
    # --------------------------------------------------------

    for indice, item in enumerate(
        serie
    ):

        try:

            dt = _converter_data_met(
                item[
                    "time"
                ]
            )

        except Exception:
            continue

        dados = item.get(
            "data",
            {},
        )

        instant = (
            dados.get(
                "instant",
                {},
            )
            .get(
                "details",
                {},
            )
        )

        temperatura = _numero_seguro(
            instant.get(
                "air_temperature"
            )
        )

        rajada = _numero_seguro(
            instant.get(
                "wind_speed_of_gust",
                instant.get(
                    "wind_speed",
                    0,
                ),
            )
        )

        simbolo = None
        chuva = 0.0
        probabilidade = 0.0
        horas_intervalo = 0

        # ----------------------------------------------------
        # Descobre o espacamento real ate o proximo ponto.
        # Isso evita somar janelas de 6h sobrepostas.
        # ----------------------------------------------------

        proximo_dt = None

        if indice + 1 < len(
            serie
        ):

            try:

                proximo_dt = (
                    _converter_data_met(
                        serie[
                            indice + 1
                        ][
                            "time"
                        ]
                    )
                )

            except Exception:
                proximo_dt = None

        if proximo_dt:

            horas_intervalo = (
                proximo_dt - dt
            ).total_seconds() / 3600

        # ----------------------------------------------------
        # SERIE HORARIA
        # ----------------------------------------------------

        if (
            horas_intervalo <= 1.5
            or horas_intervalo == 0
        ):

            periodo = dados.get(
                "next_1_hours"
            )

            if periodo:

                chuva = (
                    _precipitacao_periodo_met(
                        periodo
                    )
                )

                probabilidade = (
                    _probabilidade_periodo_met(
                        periodo
                    )
                )

                simbolo = (
                    periodo
                    .get(
                        "summary",
                        {},
                    )
                    .get(
                        "symbol_code"
                    )
                )

                horas_intervalo = 1

        # ----------------------------------------------------
        # SERIE EM INTERVALOS MAIORES
        # ----------------------------------------------------

        if (
            simbolo is None
            and horas_intervalo <= 6.5
        ):

            periodo = dados.get(
                "next_6_hours"
            )

            if periodo:

                chuva = (
                    _precipitacao_periodo_met(
                        periodo
                    )
                )

                probabilidade = (
                    _probabilidade_periodo_met(
                        periodo
                    )
                )

                simbolo = (
                    periodo
                    .get(
                        "summary",
                        {},
                    )
                    .get(
                        "symbol_code"
                    )
                )

                horas_intervalo = 6

        if simbolo is None:

            for chave_periodo in (
                "next_1_hours",
                "next_6_hours",
                "next_12_hours",
            ):

                periodo = dados.get(
                    chave_periodo
                )

                if not periodo:
                    continue

                simbolo = (
                    periodo
                    .get(
                        "summary",
                        {},
                    )
                    .get(
                        "symbol_code"
                    )
                )

                if simbolo:
                    break

        pontos.append(
            {
                "dt":
                    dt.replace(
                        tzinfo=None
                    ),

                "temperatura":
                    temperatura,

                "rajada":
                    rajada,

                "chuva":
                    chuva,

                "probabilidade":
                    probabilidade,

                "simbolo":
                    simbolo,

                "horas_intervalo":
                    horas_intervalo,
            }
        )

    if not pontos:

        raise RuntimeError(
            "Nao foi possivel interpretar "
            "a previsao do MET Norway."
        )

    # --------------------------------------------------------
    # CHUVA 24H / 72H
    # --------------------------------------------------------

    agora_local = datetime.now()

    limite_24 = (
        agora_local
        + timedelta(
            hours=24
        )
    )

    limite_72 = (
        agora_local
        + timedelta(
            hours=72
        )
    )

    chuva_24h = sum(
        p["chuva"]
        for p in pontos
        if (
            p["dt"] >= agora_local
            and p["dt"] < limite_24
        )
    )

    chuva_72h = sum(
        p["chuva"]
        for p in pontos
        if (
            p["dt"] >= agora_local
            and p["dt"] < limite_72
        )
    )

    # --------------------------------------------------------
    # AGRUPAMENTO DIARIO
    # --------------------------------------------------------

    grupos = {}

    for ponto in pontos:

        data = ponto[
            "dt"
        ].date()

        grupos.setdefault(
            data,
            [],
        ).append(
            ponto
        )

    dias = []

    datas_ordenadas = sorted(
        grupos.keys()
    )[:7]

    for data in datas_ordenadas:

        registros = grupos[
            data
        ]

        temperaturas = [
            r["temperatura"]
            for r in registros
        ]

        rajadas = [
            r["rajada"]
            for r in registros
        ]

        chuva_dia = sum(
            r["chuva"]
            for r in registros
        )

        probabilidade = max(
            (
                r["probabilidade"]
                for r in registros
            ),
            default=0,
        )

        # Escolhe simbolo proximo do meio-dia.
        simbolo_registro = min(
            registros,
            key=lambda r:
                abs(
                    r["dt"].hour
                    - 12
                ),
        )

        descricao, icone = (
            _descricao_met(
                simbolo_registro[
                    "simbolo"
                ]
            )
        )

        dt_data = datetime.combine(
            data,
            datetime.min.time(),
        )

        dias.append(
            {
                "data":
                    data.isoformat(),

                "dia_semana":
                    (
                        "HOJE"
                        if (
                            data
                            == agora_local.date()
                        )
                        else nome_dia(
                            dt_data
                        )
                    ),

                "data_curta":
                    dt_data.strftime(
                        "%d/%m"
                    ),

                "codigo":
                    simbolo_registro[
                        "simbolo"
                    ],

                "descricao":
                    descricao,

                "icone":
                    icone,

                "maxima":
                    round(
                        max(
                            temperaturas
                        ),
                        1,
                    ),

                "minima":
                    round(
                        min(
                            temperaturas
                        ),
                        1,
                    ),

                "chuva":
                    round(
                        chuva_dia,
                        1,
                    ),

                "probabilidade":
                    int(
                        round(
                            probabilidade
                        )
                    ),

                "rajada":
                    round(
                        max(
                            rajadas
                        ),
                        1,
                    ),
            }
        )

    chuva_7d = sum(
        dia["chuva"]
        for dia in dias
    )

    mais_chuvoso = None

    if dias:

        mais_chuvoso = max(
            dias,
            key=lambda d:
                d["chuva"],
        )

    return {
        "ok": True,

        "chave_local":
            local,

        "local":
            cfg["nome"],

        "titulo":
            cfg["titulo"],

        "subtitulo":
            cfg["subtitulo"],

        "latitude":
            cfg["latitude"],

        "longitude":
            cfg["longitude"],

        "atualizado_em":
            agora_local.isoformat(
                timespec="minutes"
            ),

        "chuva_24h":
            round(
                chuva_24h,
                1,
            ),

        "chuva_72h":
            round(
                chuva_72h,
                1,
            ),

        "chuva_7d":
            round(
                chuva_7d,
                1,
            ),

        "mais_chuvoso":
            mais_chuvoso,

        "dias":
            dias,

        "fonte":
            "MET Norway",

        "cache":
            False,

        "fallback":
            True,
    }


def _buscar_met_norway():

    resultados = {}

    for local in LOCAIS:

        bruto = _buscar_met_local(
            local
        )

        resultados[
            local
        ] = _montar_met_local(
            local,
            bruto,
        )

    return resultados


# ============================================================
# MOTOR MULTIFONTE
# ============================================================

def _buscar_previsoes():

    erro_openmeteo = None

    # --------------------------------------------------------
    # FONTE 1 — OPEN-METEO
    # --------------------------------------------------------

    try:

        resultados = (
            _buscar_openmeteo()
        )

        print(
            "[METEO] Fonte: Open-Meteo.",
            flush=True,
        )

        return (
            resultados,
            "Open-Meteo",
            None,
        )

    except Exception as e:

        erro_openmeteo = str(
            e
        )

        print(
            (
                "[METEO] Open-Meteo falhou: "
                + erro_openmeteo
            ),
            flush=True,
        )

    # --------------------------------------------------------
    # FONTE 2 — MET NORWAY
    # --------------------------------------------------------

    try:

        resultados = (
            _buscar_met_norway()
        )

        print(
            (
                "[METEO] Fonte alternativa "
                "ativada: MET Norway."
            ),
            flush=True,
        )

        return (
            resultados,
            "MET Norway",
            erro_openmeteo,
        )

    except Exception as e:

        erro_met = str(
            e
        )

        print(
            (
                "[METEO] MET Norway falhou: "
                + erro_met
            ),
            flush=True,
        )

        raise RuntimeError(
            (
                "Open-Meteo: "
                + erro_openmeteo
                + " | MET Norway: "
                + erro_met
            )
        )


def obter_previsao_semana(
    local="santa_tereza",
    forcar=False,
):

    if local not in LOCAIS:

        raise ValueError(
            (
                "Local meteorologico "
                "desconhecido: "
                f"{local}"
            )
        )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if (
        not forcar
        and _cache_valido()
    ):

        resultado = (
            _resultado_cache(
                local
            )
        )

        if resultado:
            return resultado

    # --------------------------------------------------------
    # ATUALIZACAO
    # --------------------------------------------------------

    try:

        (
            resultados,
            fonte,
            erro_principal,
        ) = _buscar_previsoes()

        agora = datetime.now()

        _CACHE_GERAL[
            "em"
        ] = agora

        _CACHE_GERAL[
            "dados"
        ] = resultados

        _CACHE_GERAL[
            "fonte"
        ] = fonte

        _CACHE_GERAL[
            "ultimo_erro"
        ] = erro_principal

        _CACHE_GERAL[
            "ultimo_erro_em"
        ] = (
            agora
            if erro_principal
            else None
        )

        for chave, resultado in (
            resultados.items()
        ):

            _CACHE[
                chave
            ] = {
                "em":
                    agora,

                "dados":
                    resultado,
            }

        return resultados[
            local
        ]

    except Exception as e:

        # ----------------------------------------------------
        # ULTIMO DADO VALIDO
        # ----------------------------------------------------

        anterior = (
            _CACHE_GERAL
            .get(
                "dados",
                {},
            )
            .get(
                local
            )
        )

        if anterior:

            copia = dict(
                anterior
            )

            copia[
                "cache"
            ] = True

            copia[
                "dados_desatualizados"
            ] = True

            copia[
                "aviso"
            ] = (
                "As fontes meteorologicas "
                "estao temporariamente "
                "indisponiveis. Exibindo "
                "a ultima previsao valida."
            )

            print(
                (
                    "[METEO] Usando ultima "
                    "previsao valida: "
                    + str(e)
                ),
                flush=True,
            )

            return copia

        raise


# ============================================================
# FUNCAO SEGURA
# ============================================================

def obter_previsao_segura(
    local="santa_tereza",
):

    try:

        return obter_previsao_semana(
            local=local
        )

    except Exception as e:

        cfg = LOCAIS.get(
            local,
            {},
        )

        return {
            "ok":
                False,

            "chave_local":
                local,

            "local":
                cfg.get(
                    "nome",
                    local,
                ),

            "titulo":
                cfg.get(
                    "titulo",
                    (
                        "PREVISAO "
                        "METEOROLOGICA "
                        "— 7 DIAS"
                    ),
                ),

            "subtitulo":
                cfg.get(
                    "subtitulo",
                    "",
                ),

            "erro":
                (
                    "Previsao meteorologica "
                    "temporariamente indisponivel."
                ),

            "erro_tecnico":
                str(
                    e
                ),

            "dias":
                [],
        }


# ============================================================
# CSS
#
# IMPORTANTE:
# FICA FORA DE F-STRING.
# ASSIM AS CHAVES CSS NAO CAUSAM ERRO DE PYTHON.
# ============================================================

CSS_PREVISAO = """
<style>

.previsao-semanal {
    margin-top:18px;
    margin-bottom:18px;
    padding:20px;
    border-radius:16px;
    background:#151e23;
    border:1px solid #2b3941;
    color:#f4f7f8;
}

.prev-cabecalho {
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:16px;
    margin-bottom:16px;
}

.prev-titulo {
    font-size:15px;
    font-weight:800;
    letter-spacing:.04em;
    color:#8fb8d0;
}

.prev-subtitulo {
    margin-top:4px;
    color:#93a9b5;
    font-size:12px;
}

.prev-resumo {
    display:grid;
    grid-template-columns:
        repeat(4,minmax(0,1fr));
    gap:10px;
    margin-bottom:18px;
}

.prev-resumo-card {
    border-radius:12px;
    background:#0c1418;
    padding:13px 14px;
    border:1px solid #26343b;
}

.prev-resumo-card span {
    display:block;
    color:#7ea0b3;
    font-size:11px;
    margin-bottom:5px;
}

.prev-resumo-card strong {
    display:block;
    color:#fff;
    font-size:19px;
}

.prev-dias {
    display:grid;
    grid-template-columns:
        repeat(7,minmax(130px,1fr));
    gap:10px;
    overflow-x:auto;
    padding-bottom:3px;
}

.prev-dia {
    min-width:130px;
    border:1px solid #2a3941;
    border-radius:13px;
    padding:12px;
    background:#10191e;
}

.prev-chuva-moderada {
    border-color:#526d7c;
}

.prev-chuva-forte {
    border-color:#a67d32;
    background:#1b1a13;
}

.prev-dia-topo {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:8px;
    font-size:12px;
    color:#819ba9;
}

.prev-dia-topo strong {
    color:#dcebf2;
    font-size:13px;
}

.prev-icone {
    font-size:30px;
    margin-top:10px;
    margin-bottom:5px;
}

.prev-condicao {
    min-height:34px;
    font-size:12px;
    color:#b1c2ca;
    margin-bottom:8px;
}

.prev-temp {
    display:flex;
    align-items:baseline;
    gap:7px;
    margin-bottom:10px;
}

.prev-temp strong {
    font-size:21px;
    color:#fff;
}

.prev-temp span {
    font-size:14px;
    color:#8095a0;
}

.prev-linha {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    padding-top:6px;
    margin-top:6px;
    border-top:1px solid #26343b;
    font-size:11px;
}

.prev-linha span {
    color:#819aa7;
}

.prev-linha strong {
    color:#f4f7f8;
}

.prev-rodape {
    margin-top:12px;
    color:#6f8793;
    font-size:10px;
}

.prev-indisponivel {
    margin-top:10px;
    color:#b3c4cc;
    font-size:13px;
}

@media (max-width:900px) {

    .prev-resumo {
        grid-template-columns:
            repeat(2,minmax(0,1fr));
    }

    .prev-dias {
        grid-template-columns:
            repeat(7,138px);
    }
}

@media (max-width:560px) {

    .previsao-semanal {
        padding:14px;
    }

    .prev-cabecalho {
        display:block;
    }

    .prev-resumo {
        grid-template-columns:
            repeat(2,minmax(0,1fr));
    }

    .prev-dia {
        min-width:132px;
    }
}

</style>
"""


# ============================================================
# HTML
# ============================================================

def gerar_html_previsao_semana(
    previsao,
):

    if not previsao:

        return (
            CSS_PREVISAO
            + """
<section class="previsao-semanal">

    <div class="prev-titulo">
        PREVISÃO METEOROLÓGICA — 7 DIAS
    </div>

    <div class="prev-indisponivel">
        Previsão meteorológica ainda não carregada.
    </div>

</section>
"""
        )

    titulo = escape(
        previsao.get(
            "titulo",
            "PREVISÃO METEOROLÓGICA — 7 DIAS",
        )
    )

    subtitulo = escape(
        previsao.get(
            "subtitulo",
            "",
        )
    )

    if not previsao.get("ok"):

        erro = escape(
            str(
                previsao.get(
                    "erro",
                    "Dados indisponíveis.",
                )
            )
        )

        return (
            CSS_PREVISAO
            + f"""
<section class="previsao-semanal">

    <div class="prev-titulo">
        {titulo}
    </div>

    <div class="prev-subtitulo">
        {subtitulo}
    </div>

    <div class="prev-indisponivel">
        {erro}
    </div>

</section>
"""
        )

    dias_html = []

    for dia in previsao.get(
        "dias",
        [],
    ):

        chuva = float(
            dia.get(
                "chuva",
                0,
            )
            or 0
        )

        classe = ""

        if chuva >= 30:

            classe = (
                " prev-chuva-forte"
            )

        elif chuva >= 10:

            classe = (
                " prev-chuva-moderada"
            )

        dias_html.append(
            f"""
<div class="prev-dia{classe}">

    <div class="prev-dia-topo">

        <strong>
            {escape(dia["dia_semana"])}
        </strong>

        <span>
            {escape(dia["data_curta"])}
        </span>

    </div>

    <div class="prev-icone">
        {dia["icone"]}
    </div>

    <div class="prev-condicao">
        {escape(dia["descricao"])}
    </div>

    <div class="prev-temp">

        <strong>
            {dia["maxima"]:.0f}°
        </strong>

        <span>
            {dia["minima"]:.0f}°
        </span>

    </div>

    <div class="prev-linha">
        <span>Chuva</span>
        <strong>
            {dia["chuva"]:.1f} mm
        </strong>
    </div>

    <div class="prev-linha">
        <span>Prob.</span>
        <strong>
            {dia["probabilidade"]}%
        </strong>
    </div>

    <div class="prev-linha">
        <span>Rajada</span>
        <strong>
            {dia["rajada"]:.0f} km/h
        </strong>
    </div>

</div>
"""
        )

    mais_chuvoso = previsao.get(
        "mais_chuvoso"
    )

    if mais_chuvoso:

        texto_mais_chuvoso = (
            f'{mais_chuvoso["dia_semana"]} '
            f'{mais_chuvoso["data_curta"]} · '
            f'{mais_chuvoso["chuva"]:.1f} mm'
        )

    else:

        texto_mais_chuvoso = "-"

    atualizado = escape(
        previsao.get(
            "atualizado_em",
            "-",
        ).replace(
            "T",
            " ",
        )
    )

    local = escape(
        previsao.get(
            "local",
            "-",
        )
    )

    fonte = escape(
        previsao.get(
            "fonte",
            "Open-Meteo",
        )
    )

    aviso_fonte = ""

    if previsao.get(
        "fallback"
    ):

        aviso_fonte = (
            " Fonte alternativa ativada "
            "automaticamente."
        )

    corpo = f"""
<section
    class="previsao-semanal"
    data-local="{escape(previsao.get("chave_local", ""))}"
>

    <div class="prev-cabecalho">

        <div>

            <div class="prev-titulo">
                {titulo}
            </div>

            <div class="prev-subtitulo">
                {subtitulo}
            </div>

        </div>

    </div>

    <div class="prev-resumo">

        <div class="prev-resumo-card">

            <span>
                Chuva próximas 24h
            </span>

            <strong>
                {previsao["chuva_24h"]:.1f} mm
            </strong>

        </div>

        <div class="prev-resumo-card">

            <span>
                Chuva próximas 72h
            </span>

            <strong>
                {previsao["chuva_72h"]:.1f} mm
            </strong>

        </div>

        <div class="prev-resumo-card">

            <span>
                Chuva prevista 7 dias
            </span>

            <strong>
                {previsao["chuva_7d"]:.1f} mm
            </strong>

        </div>

        <div class="prev-resumo-card">

            <span>
                Maior previsão diária
            </span>

            <strong style="font-size:15px">
                {escape(texto_mais_chuvoso)}
            </strong>

        </div>

    </div>

    <div class="prev-dias">
        {''.join(dias_html)}
    </div>

    <div class="prev-rodape">
        Local: {local}.
        Atualização meteorológica: {atualizado}.
        Fonte: {fonte}.{aviso_fonte}
        Dados meteorológicos são previsão e
        não substituem alertas oficiais.
    </div>

</section>
"""

    return (
        CSS_PREVISAO
        + corpo
    )
