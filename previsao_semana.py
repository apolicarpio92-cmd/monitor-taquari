from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

import requests


# ============================================================
# SANTA TEREZA / RS
# ============================================================

LATITUDE = -29.1781
LONGITUDE = -51.7322

URL = "https://api.open-meteo.com/v1/forecast"

TIMEZONE = "America/Sao_Paulo"

CACHE_SEGUNDOS = 1800

_cache = None
_cache_em = None


# ============================================================
# CODIGOS WMO
# ============================================================

def descricao_tempo(codigo):

    mapa = {
        0: ("Céu limpo", "☀"),
        1: ("Predomínio de sol", "🌤"),
        2: ("Parcialmente nublado", "⛅"),
        3: ("Nublado", "☁"),
        45: ("Nevoeiro", "🌫"),
        48: ("Nevoeiro", "🌫"),
        51: ("Garoa fraca", "🌦"),
        53: ("Garoa", "🌦"),
        55: ("Garoa intensa", "🌧"),
        56: ("Garoa congelante", "🌧"),
        57: ("Garoa congelante forte", "🌧"),
        61: ("Chuva fraca", "🌦"),
        63: ("Chuva moderada", "🌧"),
        65: ("Chuva forte", "🌧"),
        66: ("Chuva congelante", "🌧"),
        67: ("Chuva congelante forte", "🌧"),
        71: ("Neve fraca", "❄"),
        73: ("Neve", "❄"),
        75: ("Neve forte", "❄"),
        77: ("Grãos de neve", "❄"),
        80: ("Pancadas fracas", "🌦"),
        81: ("Pancadas", "🌧"),
        82: ("Pancadas fortes", "⛈"),
        85: ("Pancadas de neve", "❄"),
        86: ("Neve forte", "❄"),
        95: ("Trovoadas", "⛈"),
        96: ("Trovoadas com granizo", "⛈"),
        99: ("Trovoadas fortes", "⛈"),
    }

    try:
        codigo = int(codigo)
    except Exception:
        codigo = -1

    return mapa.get(
        codigo,
        ("Condição variável", "🌤")
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
            casas
        )
    except Exception:
        return 0.0


# ============================================================
# COLETA
# ============================================================

def obter_previsao_semana(forcar=False):

    global _cache
    global _cache_em

    agora = datetime.now()

    if (
        not forcar
        and _cache is not None
        and _cache_em is not None
        and (
            agora - _cache_em
        ).total_seconds() < CACHE_SEGUNDOS
    ):
        return _cache

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": TIMEZONE,
        "forecast_days": 7,

        "hourly": ",".join([
            "precipitation",
            "precipitation_probability",
        ]),

        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "wind_gusts_10m_max",
        ]),
    }

    r = requests.get(
        URL,
        params=params,
        timeout=20,
    )

    r.raise_for_status()

    dados = r.json()

    hourly = dados.get(
        "hourly",
        {}
    )

    daily = dados.get(
        "daily",
        {}
    )

    # ========================================================
    # ACUMULADOS HORARIOS
    # ========================================================

    horas = hourly.get(
        "time",
        []
    )

    precipitacao_hora = hourly.get(
        "precipitation",
        []
    )

    registros_horarios = []

    for indice, texto_data in enumerate(horas):

        try:
            dt = datetime.fromisoformat(
                texto_data
            )
        except Exception:
            continue

        if dt < agora.replace(
            minute=0,
            second=0,
            microsecond=0,
        ):
            continue

        try:
            chuva = float(
                precipitacao_hora[indice]
                or 0
            )
        except Exception:
            chuva = 0.0

        registros_horarios.append(
            (
                dt,
                chuva,
            )
        )

    limite_24 = agora + timedelta(
        hours=24
    )

    limite_72 = agora + timedelta(
        hours=72
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

    # ========================================================
    # PREVISAO DIARIA
    # ========================================================

    datas = daily.get(
        "time",
        []
    )

    codigos = daily.get(
        "weather_code",
        []
    )

    maximas = daily.get(
        "temperature_2m_max",
        []
    )

    minimas = daily.get(
        "temperature_2m_min",
        []
    )

    chuvas = daily.get(
        "precipitation_sum",
        []
    )

    probabilidades = daily.get(
        "precipitation_probability_max",
        []
    )

    rajadas = daily.get(
        "wind_gusts_10m_max",
        []
    )

    dias = []

    for i, data_texto in enumerate(datas):

        try:
            dt = datetime.fromisoformat(
                data_texto
            )
        except Exception:
            continue

        codigo = (
            codigos[i]
            if i < len(codigos)
            else None
        )

        descricao, icone = descricao_tempo(
            codigo
        )

        dia = {
            "data": data_texto,
            "dia_semana": (
                "HOJE"
                if dt.date() == agora.date()
                else nome_dia(dt)
            ),
            "data_curta": dt.strftime(
                "%d/%m"
            ),
            "codigo": codigo,
            "descricao": descricao,
            "icone": icone,
            "maxima": numero(
                maximas[i]
                if i < len(maximas)
                else 0
            ),
            "minima": numero(
                minimas[i]
                if i < len(minimas)
                else 0
            ),
            "chuva": numero(
                chuvas[i]
                if i < len(chuvas)
                else 0
            ),
            "probabilidade": int(
                numero(
                    probabilidades[i]
                    if i < len(probabilidades)
                    else 0,
                    0,
                )
            ),
            "rajada": numero(
                rajadas[i]
                if i < len(rajadas)
                else 0
            ),
        }

        dias.append(
            dia
        )

    chuva_7d = sum(
        d["chuva"]
        for d in dias
    )

    mais_chuvoso = None

    if dias:

        mais_chuvoso = max(
            dias,
            key=lambda d: d[
                "chuva"
            ],
        )

    resultado = {
        "ok": True,
        "local": "Santa Tereza - RS",
        "atualizado_em": agora.isoformat(
            timespec="minutes"
        ),
        "chuva_24h": round(
            chuva_24h,
            1
        ),
        "chuva_72h": round(
            chuva_72h,
            1
        ),
        "chuva_7d": round(
            chuva_7d,
            1
        ),
        "mais_chuvoso": mais_chuvoso,
        "dias": dias,
    }

    _cache = resultado
    _cache_em = agora

    return resultado


# ============================================================
# HTML
# ============================================================

def gerar_html_previsao_semana(
    previsao
):

    if not previsao:

        return """
        <section
            id="previsao-semanal-taquari"
            class="previsao-semanal"
        >
            <div class="prev-titulo">
                PREVISÃO METEOROLÓGICA — 7 DIAS
            </div>

            <div class="prev-indisponivel">
                Previsão meteorológica ainda não carregada.
            </div>
        </section>
        """

    if not previsao.get(
        "ok"
    ):

        erro = escape(
            str(
                previsao.get(
                    "erro",
                    "Dados indisponíveis."
                )
            )
        )

        return f"""
        <section
            id="previsao-semanal-taquari"
            class="previsao-semanal"
        >
            <div class="prev-titulo">
                PREVISÃO METEOROLÓGICA — 7 DIAS
            </div>

            <div class="prev-indisponivel">
                {erro}
            </div>
        </section>
        """

    dias_html = []

    for dia in previsao.get(
        "dias",
        []
    ):

        chuva = dia.get(
            "chuva",
            0
        )

        destaque_chuva = (
            " prev-chuva-forte"
            if chuva >= 30
            else ""
        )

        dias_html.append(
            f"""
            <div class="prev-dia{destaque_chuva}">

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
            "-"
        ).replace(
            "T",
            " "
        )
    )

    return f"""
    <style>

    .previsao-semanal {{
        margin-top: 18px;
        margin-bottom: 18px;
        padding: 20px;
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid #dfe5df;
        box-shadow:
            0 3px 12px rgba(0,0,0,.05);
    }}

    .prev-cabecalho {{
        display:flex;
        align-items:flex-start;
        justify-content:space-between;
        gap:16px;
        margin-bottom:16px;
    }}

    .prev-titulo {{
        font-size:15px;
        font-weight:800;
        letter-spacing:.03em;
        color:#292f12;
    }}

    .prev-subtitulo {{
        margin-top:4px;
        color:#69706a;
        font-size:12px;
    }}

    .prev-resumo {{
        display:grid;
        grid-template-columns:
            repeat(4, minmax(0, 1fr));
        gap:10px;
        margin-bottom:18px;
    }}

    .prev-resumo-card {{
        border-radius:12px;
        background:#f5f7f2;
        padding:12px 14px;
        border:1px solid #e2e7df;
    }}

    .prev-resumo-card span {{
        display:block;
        color:#747b72;
        font-size:11px;
        margin-bottom:4px;
    }}

    .prev-resumo-card strong {{
        display:block;
        color:#292f12;
        font-size:19px;
    }}

    .prev-dias {{
        display:grid;
        grid-template-columns:
            repeat(7, minmax(130px, 1fr));
        gap:10px;
        overflow-x:auto;
        padding-bottom:2px;
    }}

    .prev-dia {{
        min-width:130px;
        border:1px solid #e3e7df;
        border-radius:13px;
        padding:12px;
        background:#fafbf8;
    }}

    .prev-chuva-forte {{
        border-color:#9fac8b;
        background:#f1f4ec;
    }}

    .prev-dia-topo {{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:8px;
        font-size:12px;
        color:#60665d;
    }}

    .prev-dia-topo strong {{
        color:#292f12;
        font-size:13px;
    }}

    .prev-icone {{
        font-size:30px;
        margin-top:10px;
        margin-bottom:5px;
    }}

    .prev-condicao {{
        min-height:34px;
        font-size:12px;
        color:#525950;
        margin-bottom:8px;
    }}

    .prev-temp {{
        display:flex;
        align-items:baseline;
        gap:7px;
        margin-bottom:10px;
    }}

    .prev-temp strong {{
        font-size:20px;
        color:#292f12;
    }}

    .prev-temp span {{
        font-size:14px;
        color:#899087;
    }}

    .prev-linha {{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:8px;
        padding-top:5px;
        margin-top:5px;
        border-top:1px solid #e7eae4;
        font-size:11px;
    }}

    .prev-linha span {{
        color:#7a8178;
    }}

    .prev-linha strong {{
        color:#353b2d;
    }}

    .prev-rodape {{
        margin-top:12px;
        color:#81877e;
        font-size:10px;
    }}

    .prev-indisponivel {{
        margin-top:10px;
        color:#777;
        font-size:13px;
    }}

    @media (max-width: 900px) {{

        .prev-resumo {{
            grid-template-columns:
                repeat(2, minmax(0, 1fr));
        }}

        .prev-dias {{
            grid-template-columns:
                repeat(7, 138px);
        }}
    }}

    @media (max-width: 560px) {{

        .previsao-semanal {{
            padding:14px;
        }}

        .prev-cabecalho {{
            display:block;
        }}

        .prev-resumo {{
            grid-template-columns:
                repeat(2, minmax(0, 1fr));
        }}
    }}

    </style>

    <section
        id="previsao-semanal-taquari"
        class="previsao-semanal"
    >

        <div class="prev-cabecalho">

            <div>

                <div class="prev-titulo">
                    PREVISÃO METEOROLÓGICA — 7 DIAS
                </div>

                <div class="prev-subtitulo">
                    Santa Tereza · foco em precipitação
                    para acompanhamento hidrológico
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
            Atualização meteorológica:
            {atualizado}.
            Fonte: Open-Meteo.
            Dados meteorológicos são previsão e
            não substituem alertas oficiais.
        </div>

    </section>
    """


def obter_previsao_segura():

    try:

        return obter_previsao_semana()

    except Exception as e:

        return {
            "ok": False,
            "erro": str(e),
            "dias": [],
        }
