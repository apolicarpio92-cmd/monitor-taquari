from __future__ import annotations

import csv
import json
import math
import os
import statistics
import time
import traceback
import webbrowser

from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import requests


from barragens import coletar_barragens


# ============================================================
# CONFIGURACAO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DIR_DADOS = BASE_DIR / "dados"
DIR_HIST = BASE_DIR / "historico"
DIR_LOG = BASE_DIR / "logs"

ARQ_HIST = DIR_HIST / "telemetria_historico.csv"
ARQ_STATUS = DIR_DADOS / "status.json"
ARQ_DASH = BASE_DIR / "dashboard_v3.html"

INTERVALO = 300
TIMEOUT = 40

ANA_URL = (
    "https://telemetriaws1.ana.gov.br/"
    "ServiceANA.asmx/DadosHidrometeorologicos"
)

ESTACOES = {
    "Santa Tereza": {
        "codigo": "86472600",
    },
    "Linha Jose Julio": {
        "codigo": "86472000",
    },
}

# Coordenadas aproximadas das localidades para previsao meteorologica.
LOCAIS_METEO = {
    "Santa Tereza": {
        "lat": -29.1781,
        "lon": -51.7322,
    },
    "Cabeceiras": {
        "lat": -28.50,
        "lon": -50.95,
    },
}



# ============================================================
# WHATSAPP
# ============================================================

DESTINATARIOS_WHATSAPP = [
    "5554996300152",
    "5554999881015",
]

ARQ_WHATSAPP_ESTADO = (
    DIR_DADOS
    / "whatsapp_estado.json"
)

# ============================================================
# LOG
# ============================================================

def log(msg):

    agora = datetime.now().strftime(
        "%d/%m/%Y %H:%M:%S"
    )

    linha = f"[{agora}] {msg}"

    print(
        linha,
        flush=True
    )

    arquivo = (
        DIR_LOG
        / f"monitor_{datetime.now():%Y%m%d}.log"
    )

    arquivo.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with arquivo.open(
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            linha + "\n"
        )


# ============================================================
# PREPARA DIRETORIOS
# ============================================================

def preparar():

    for p in [
        DIR_DADOS,
        DIR_HIST,
        DIR_LOG,
    ]:
        p.mkdir(
            parents=True,
            exist_ok=True
        )


# ============================================================
# XML
# ============================================================

def limpar_tag(tag):

    if "}" in tag:
        return tag.split(
            "}",
            1
        )[1]

    return tag


def converter_data(valor):

    formatos = [
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]

    for formato in formatos:

        try:
            return datetime.strptime(
                valor,
                formato
            )
        except Exception:
            pass

    return None


# ============================================================
# ANA
# ============================================================

def buscar_ana(
    nome,
    codigo,
):

    agora = datetime.now()

    params = {
        "codEstacao": codigo,
        "dataInicio": (
            agora - timedelta(days=2)
        ).strftime("%d/%m/%Y"),
        "dataFim": agora.strftime(
            "%d/%m/%Y"
        ),
    }

    # ========================================================
    # ANA - TENTATIVA PRINCIPAL + FALLBACK
    # ========================================================

    urls_ana = [
        (
            ANA_URL,
            "FILTRADO"
        ),
        (
            "https://telemetriaws1.ana.gov.br/"
            "ServiceANA.asmx/"
            "DadosHidrometeorologicosGerais",
            "GERAL"
        ),
    ]

    resposta = None
    ultimo_erro = None

    for url_ana, tipo_ana in urls_ana:

        try:

            resposta_teste = requests.get(
                url_ana,
                params=params,
                timeout=TIMEOUT,
                headers={
                    "User-Agent":
                        "Monitor-Taquari-V3/1.0"
                },
            )

            resposta_teste.raise_for_status()

            if not resposta_teste.text.strip():

                raise RuntimeError(
                    "Resposta vazia da ANA"
                )

            resposta = resposta_teste

            if tipo_ana == "GERAL":

                log(
                    f"ANA {nome}: endpoint GERAL "
                    "utilizado como fallback."
                )

            break

        except Exception as e:

            ultimo_erro = e

            log(
                f"ANA {nome}: falha endpoint "
                f"{tipo_ana}: {e}"
            )

    if resposta is None:

        # ====================================================
        # FALLBACK LOCAL
        #
        # Se os endpoints da ANA falharem, nao apagamos
        # a ultima leitura valida. Recuperamos o historico
        # local ja salvo pelo monitor.
        # ====================================================

        arquivo_historico = (
            BASE
            / "historico"
            / "telemetria_historico.csv"
        )

        dados_locais = []

        if arquivo_historico.exists():

            try:

                with arquivo_historico.open(
                    "r",
                    encoding="utf-8-sig",
                    newline=""
                ) as f:

                    reader = csv.DictReader(
                        f,
                        delimiter=";"
                    )

                    for row in reader:

                        estacao_row = (
                            row.get("estacao")
                            or row.get("nome")
                            or ""
                        ).strip()

                        codigo_row = (
                            row.get("codigo")
                            or row.get("codEstacao")
                            or ""
                        ).strip()

                        if (
                            estacao_row != nome
                            and codigo_row != str(codigo)
                        ):
                            continue

                        data_txt = (
                            row.get("data_hora")
                            or row.get("DataHora")
                            or ""
                        ).strip()

                        if not data_txt:
                            continue

                        dt = None

                        formatos = [
                            "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%d %H:%M",
                            "%d/%m/%Y %H:%M:%S",
                            "%d/%m/%Y %H:%M",
                        ]

                        for formato in formatos:

                            try:

                                dt = datetime.strptime(
                                    data_txt,
                                    formato
                                )

                                break

                            except Exception:
                                pass

                        if dt is None:
                            continue

                        nivel_txt = (
                            row.get("nivel_m")
                            or row.get("nivel")
                            or row.get("Nivel")
                            or ""
                        ).strip()

                        if not nivel_txt:
                            continue

                        try:

                            nivel_m = float(
                                nivel_txt.replace(
                                    ",",
                                    "."
                                )
                            )

                        except Exception:
                            continue

                        vazao = None

                        vazao_txt = (
                            row.get("vazao")
                            or row.get("Vazao")
                            or ""
                        ).strip()

                        if vazao_txt:

                            try:

                                vazao = float(
                                    vazao_txt.replace(
                                        ",",
                                        "."
                                    )
                                )

                            except Exception:
                                pass

                        chuva = None

                        chuva_txt = (
                            row.get("chuva")
                            or row.get("Chuva")
                            or ""
                        ).strip()

                        if chuva_txt:

                            try:

                                chuva = float(
                                    chuva_txt.replace(
                                        ",",
                                        "."
                                    )
                                )

                            except Exception:
                                pass

                        dados_locais.append(
                            {
                                "estacao":
                                    nome,

                                "codigo":
                                    str(codigo),

                                "data_hora":
                                    dt,

                                "nivel_m":
                                    nivel_m,

                                "vazao":
                                    vazao,

                                "chuva":
                                    chuva,

                                "fonte_ana":
                                    "HISTORICO_LOCAL",
                            }
                        )

                dados_locais = sorted(
                    dados_locais,
                    key=lambda x:
                        x["data_hora"]
                )

            except Exception as e:

                log(
                    f"ERRO fallback local {nome}: {e}"
                )

        if dados_locais:

            ultima_local = dados_locais[-1]

            log(
                f"ANA {nome}: indisponivel. "
                "Usando historico local: "
                f"{ultima_local['nivel_m']:.2f} m "
                f"de "
                f"{ultima_local['data_hora'].strftime('%d/%m/%Y %H:%M')}."
            )

            return dados_locais

        raise RuntimeError(
            f"ANA indisponivel para {nome} "
            "e nenhum historico local foi encontrado: "
            f"{ultimo_erro}"
        )

    raiz = ET.fromstring(
        resposta.content
    )

    registros = []

    for elemento in raiz.iter():

        filhos = list(
            elemento
        )

        if not filhos:
            continue

        registro = {}

        for filho in filhos:

            if list(filho):
                continue

            chave = limpar_tag(
                filho.tag
            )

            valor = (
                filho.text.strip()
                if filho.text
                else ""
            )

            registro[
                chave
            ] = valor

        if "DataHora" not in registro:
            continue

        dt = converter_data(
            registro.get(
                "DataHora",
                ""
            )
        )

        if not dt:
            continue

        try:

            nivel_cm = float(
                registro.get(
                    "Nivel",
                    ""
                )
            )

            nivel_m = (
                nivel_cm
                / 100.0
            )

        except Exception:

            continue

        try:

            vazao = float(
                registro.get(
                    "Vazao",
                    ""
                )
            )

        except Exception:

            vazao = None

        try:

            chuva = float(
                registro.get(
                    "Chuva",
                    ""
                )
            )

        except Exception:

            chuva = None

        registros.append(
            {
                "estacao": nome,
                "codigo": codigo,
                "data_hora": dt,
                "nivel_m": nivel_m,
                "vazao": vazao,
                "chuva": chuva,
            }
        )

    # remove duplicados
    unicos = {}

    for r in registros:

        chave = (
            r["estacao"],
            r["data_hora"],
        )

        unicos[
            chave
        ] = r

    return sorted(
        unicos.values(),
        key=lambda x:
            x["data_hora"]
    )


# ============================================================
# HISTORICO LOCAL
# ============================================================

def carregar_historico():

    registros = []

    if not ARQ_HIST.exists():
        return registros

    with ARQ_HIST.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(
            f,
            delimiter=";"
        )

        for row in reader:

            try:

                registros.append(
                    {
                        "estacao":
                            row["estacao"],

                        "codigo":
                            row["codigo"],

                        "data_hora":
                            datetime.strptime(
                                row["data_hora"],
                                "%Y-%m-%d %H:%M:%S"
                            ),

                        "nivel_m":
                            float(
                                row["nivel_m"]
                                .replace(",", ".")
                            ),

                        "vazao":
                            (
                                float(
                                    row["vazao"]
                                    .replace(",", ".")
                                )
                                if row.get(
                                    "vazao"
                                )
                                else None
                            ),

                        "chuva":
                            (
                                float(
                                    row["chuva"]
                                    .replace(",", ".")
                                )
                                if row.get(
                                    "chuva"
                                )
                                else None
                            ),
                    }
                )

            except Exception:
                continue

    return registros


def salvar_historico(
    novos,
):

    antigos = carregar_historico()

    combinados = {}

    for r in (
        antigos + novos
    ):

        chave = (
            r["estacao"],
            r["data_hora"],
        )

        combinados[
            chave
        ] = r

    registros = sorted(
        combinados.values(),
        key=lambda x:
            (
                x["estacao"],
                x["data_hora"],
            )
    )

    with ARQ_HIST.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.writer(
            f,
            delimiter=";"
        )

        writer.writerow(
            [
                "estacao",
                "codigo",
                "data_hora",
                "nivel_m",
                "vazao",
                "chuva",
            ]
        )

        for r in registros:

            writer.writerow(
                [
                    r["estacao"],
                    r["codigo"],
                    r["data_hora"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    f'{r["nivel_m"]:.2f}'.replace(
                        ".",
                        ","
                    ),
                    (
                        f'{r["vazao"]:.2f}'.replace(
                            ".",
                            ","
                        )
                        if r["vazao"]
                        is not None
                        else ""
                    ),
                    (
                        f'{r["chuva"]:.2f}'.replace(
                            ".",
                            ","
                        )
                        if r["chuva"]
                        is not None
                        else ""
                    ),
                ]
            )

    return registros


# ============================================================
# VELOCIDADE
# ============================================================

def velocidade_janela(
    dados,
    minutos,
):

    if len(dados) < 2:
        return None

    ultimo = dados[-1]

    alvo = (
        ultimo["data_hora"]
        - timedelta(
            minutes=minutos
        )
    )

    anterior = None

    for r in reversed(
        dados[:-1]
    ):

        if (
            r["data_hora"]
            <= alvo
        ):

            anterior = r
            break

    if anterior is None:
        anterior = dados[0]

    horas = (
        ultimo["data_hora"]
        - anterior["data_hora"]
    ).total_seconds() / 3600

    if horas <= 0:
        return None

    return (
        ultimo["nivel_m"]
        - anterior["nivel_m"]
    ) / horas


# ============================================================
# VARIABILIDADE
# ============================================================

def variabilidade(
    dados,
):

    recentes = dados[-12:]

    velocidades = []

    for a, b in zip(
        recentes[:-1],
        recentes[1:]
    ):

        horas = (
            b["data_hora"]
            - a["data_hora"]
        ).total_seconds() / 3600

        if horas <= 0:
            continue

        velocidades.append(
            (
                b["nivel_m"]
                - a["nivel_m"]
            ) / horas
        )

    if len(
        velocidades
    ) < 2:
        return 0.10

    try:

        return max(
            0.05,
            statistics.stdev(
                velocidades
            )
        )

    except Exception:

        return 0.10


# ============================================================
# MODELO EXPERIMENTAL
# ============================================================

def prever_santa(
    dados_santa,
    dados_jose,
):

    if len(
        dados_santa
    ) < 3:

        return None

    atual = dados_santa[-1]

    v30 = velocidade_janela(
        dados_santa,
        30
    )

    v60 = velocidade_janela(
        dados_santa,
        60
    )

    v120 = velocidade_janela(
        dados_santa,
        120
    )

    # velocidade-base ponderada
    candidatos = []

    if v30 is not None:
        candidatos.append(
            (
                v30,
                0.45
            )
        )

    if v60 is not None:
        candidatos.append(
            (
                v60,
                0.35
            )
        )

    if v120 is not None:
        candidatos.append(
            (
                v120,
                0.20
            )
        )

    if not candidatos:
        return None

    soma_pesos = sum(
        p
        for _, p in candidatos
    )

    velocidade = sum(
        v * p
        for v, p in candidatos
    ) / soma_pesos

    # aceleracao recente,
    # limitada para evitar extrapolacao absurda
    aceleracao = 0.0

    if (
        v30 is not None
        and v120 is not None
    ):

        aceleracao = (
            v30 - v120
        ) / 1.5

        aceleracao = max(
            -0.15,
            min(
                aceleracao,
                0.15
            )
        )

    # indicador de montante.
    # Ainda NAO altera a previsao diretamente;
    # sera calibrado depois.
    v_jose_60 = (
        velocidade_janela(
            dados_jose,
            60
        )
        if dados_jose
        else None
    )

    sigma = variabilidade(
        dados_santa
    )

    previsoes = {}

    for h in [
        1,
        2,
        3,
        6,
    ]:

        # apos 3h reduz gradualmente
        # efeito da aceleracao
        h_acel = min(
            h,
            3
        )

        estimado = (
            atual["nivel_m"]
            + velocidade * h
            + 0.5
            * aceleracao
            * (
                h_acel ** 2
            )
        )

        # incerteza cresce com horizonte
        margem = (
            0.12
            + sigma
            * math.sqrt(h)
            * 0.55
            + 0.05
            * h
        )

        previsoes[
            h
        ] = {
            "estimado":
                max(
                    0,
                    estimado
                ),

            "min":
                max(
                    0,
                    estimado - margem
                ),

            "max":
                estimado + margem,
        }

    return {
        "nivel_atual":
            atual["nivel_m"],

        "data_hora":
            atual["data_hora"],

        "v30":
            v30,

        "v60":
            v60,

        "v120":
            v120,

        "aceleracao":
            aceleracao,

        "velocidade_modelo":
            velocidade,

        "v_jose_60":
            v_jose_60,

        "previsoes":
            previsoes,
    }


# ============================================================
# METEOROLOGIA
# ============================================================

def coletar_meteorologia():

    saida = {}

    for nome, loc in (
        LOCAIS_METEO.items()
    ):

        try:

            params = {
                "latitude":
                    loc["lat"],

                "longitude":
                    loc["lon"],

                "hourly":
                    (
                        "precipitation,"
                        "precipitation_probability"
                    ),

                "forecast_days":
                    2,

                "timezone":
                    "America/Sao_Paulo",
            }

            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params,
                timeout=TIMEOUT,
            )

            r.raise_for_status()

            dados = r.json()

            hourly = dados.get(
                "hourly",
                {}
            )

            tempos = hourly.get(
                "time",
                []
            )

            chuva = hourly.get(
                "precipitation",
                []
            )

            prob = hourly.get(
                "precipitation_probability",
                []
            )

            agora = datetime.now()

            acumulados = {
                1: 0.0,
                3: 0.0,
                6: 0.0,
                12: 0.0,
            }

            prob_max = {
                1: 0.0,
                3: 0.0,
                6: 0.0,
                12: 0.0,
            }

            for ts, mm, pp in zip(
                tempos,
                chuva,
                prob
            ):

                try:

                    dt = datetime.fromisoformat(
                        ts
                    )

                    delta = (
                        dt - agora
                    ).total_seconds() / 3600

                    if (
                        delta < -0.5
                    ):
                        continue

                    mm = float(
                        mm or 0
                    )

                    pp = float(
                        pp or 0
                    )

                    for janela in acumulados:

                        if (
                            0
                            <= delta
                            <= janela
                        ):

                            acumulados[
                                janela
                            ] += mm

                            prob_max[
                                janela
                            ] = max(
                                prob_max[
                                    janela
                                ],
                                pp
                            )

                except Exception:
                    pass

            saida[
                nome
            ] = {
                "chuva":
                    acumulados,

                "prob":
                    prob_max,
            }

        except Exception as e:

            log(
                f"Meteorologia {nome}: {e}"
            )

    return saida


# ============================================================
# STATUS DA FONTE
# ============================================================

def status_fonte(
    data_hora,
):

    if not data_hora:
        return (
            "SEM DADOS",
            9999
        )

    idade = (
        datetime.now()
        - data_hora
    ).total_seconds() / 60

    if idade <= 30:
        status = "ONLINE"

    elif idade <= 60:
        status = "ATRASADO"

    else:
        status = "DEFASADO"

    return (
        status,
        idade
    )


# ============================================================
# FORMATACAO
# ============================================================

def fmt(
    valor,
    casas=2,
):

    if valor is None:
        return "-"

    return (
        f"{valor:.{casas}f}"
        .replace(
            ".",
            ","
        )
    )


def seta(
    velocidade,
):

    if velocidade is None:
        return "="

    if velocidade > 0.05:
        return "↑"

    if velocidade < -0.05:
        return "↓"

    return "="



# ============================================================
# HTML BARRAGENS
# ============================================================

def gerar_barragens_html(barragens):

    if not barragens:

        return """
        <div class="secao card">

            <div class="titulo">
                BARRAGENS — RIO DAS ANTAS
            </div>

            <div style="margin-top:15px">
                Dados das barragens indisponíveis.
            </div>

        </div>
        """

    cards = []

    for b in barragens:

        nome = b.get(
            "nome",
            "-"
        )

        sai = b.get(
            "sai"
        )

        entra = b.get(
            "entra"
        )

        nivel = b.get(
            "nivel"
        )

        seta_b = b.get(
            "seta",
            "="
        )

        pct = b.get(
            "variacao_pct"
        )

        data_hora = b.get(
            "data_hora"
        )

        if data_hora:

            hora_txt = data_hora.strftime(
                "%d/%m/%Y %H:%M"
            )

        else:

            hora_txt = "-"

        if pct is None:

            variacao_txt = (
                "aguardando próxima leitura"
            )

        else:

            sinal = (
                "+"
                if pct > 0
                else ""
            )

            variacao_txt = (
                f"{sinal}{pct:.1f}%"
            )

        sai_txt = (
            fmt(
                sai,
                0
            )
            if sai is not None
            else "-"
        )

        entra_txt = (
            fmt(
                entra,
                0
            )
            if entra is not None
            else "-"
        )

        nivel_txt = (
            fmt(
                nivel,
                2
            )
            if nivel is not None
            else "-"
        )

        cards.append(
            f"""
            <div class="card">

                <div class="titulo">
                    {nome.upper()}
                </div>

                <div class="nivel">

                    {sai_txt}

                    <span
                        style="
                            font-size:16px;
                            font-weight:500;
                        "
                    >
                        m³/s
                    </span>

                    <span class="seta">
                        {seta_b}
                    </span>

                </div>

                <div class="hora">
                    saída · {hora_txt}
                </div>

                <div class="metricas">

                    <div>

                        <span>Entrada</span>

                        <strong>
                            {entra_txt} m³/s
                        </strong>

                    </div>

                    <div>

                        <span>Variação</span>

                        <strong>
                            {variacao_txt}
                        </strong>

                    </div>

                    <div>

                        <span>Nível reservatório</span>

                        <strong>
                            {nivel_txt} m
                        </strong>

                    </div>

                </div>

            </div>
            """
        )

    return f"""
    <div class="secao">

        <div
            class="titulo"
            style="
                margin-bottom:12px;
                font-size:14px;
            "
        >
            BARRAGENS — RIO DAS ANTAS
        </div>

        <div class="grid">

            {''.join(cards)}

        </div>

    </div>
    """

# ============================================================
# DASHBOARD
# ============================================================

def gerar_dashboard(
    por_estacao,
    modelo,
    meteo,
    barragens,
):

    santa = por_estacao.get(
        "Santa Tereza",
        []
    )

    jose = por_estacao.get(
        "Linha Jose Julio",
        []
    )

    santa_atual = (
        santa[-1]
        if santa
        else None
    )

    jose_atual = (
        jose[-1]
        if jose
        else None
    )

    v_santa = (
        velocidade_janela(
            santa,
            60
        )
        if santa
        else None
    )

    v_jose = (
        velocidade_janela(
            jose,
            60
        )
        if jose
        else None
    )

    st_status, st_idade = (
        status_fonte(
            santa_atual[
                "data_hora"
            ]
        )
        if santa_atual
        else (
            "SEM DADOS",
            9999
        )
    )

    jj_status, jj_idade = (
        status_fonte(
            jose_atual[
                "data_hora"
            ]
        )
        if jose_atual
        else (
            "SEM DADOS",
            9999
        )
    )

    previsao_html = ""

    if modelo:

        for h in [
            1,
            2,
            3,
            6,
        ]:

            p = modelo[
                "previsoes"
            ][h]

            horario = (
                modelo[
                    "data_hora"
                ]
                + timedelta(
                    hours=h
                )
            ).strftime(
                "%H:%M"
            )

            rotulo = (
                "estimativa"
                if h <= 2
                else (
                    "tendencia"
                    if h == 3
                    else "cenario"
                )
            )

            previsao_html += f"""
            <div class="previsao-item">
                <span>
                    +{h}h · {horario}
                </span>

                <strong>
                    {fmt(p["estimado"])} m
                </strong>

                <small>
                    faixa {fmt(p["min"])}
                    –
                    {fmt(p["max"])} m
                    · {rotulo}
                </small>
            </div>
            """

    meteo_html = ""

    for local in [
        "Cabeceiras",
        "Santa Tereza",
    ]:

        d = meteo.get(
            local,
            {}
        )

        chuva = d.get(
            "chuva",
            {}
        )

        prob = d.get(
            "prob",
            {}
        )

        meteo_html += f"""
        <div class="card">
            <div class="titulo">
                CHUVA — {local}
            </div>

            <div class="chuva-grid">

                <div>
                    <span>+1h</span>
                    <strong>
                        {fmt(chuva.get(1))} mm
                    </strong>
                </div>

                <div>
                    <span>+3h</span>
                    <strong>
                        {fmt(chuva.get(3))} mm
                    </strong>
                </div>

                <div>
                    <span>+6h</span>
                    <strong>
                        {fmt(chuva.get(6))} mm
                    </strong>
                </div>

                <div>
                    <span>+12h</span>
                    <strong>
                        {fmt(chuva.get(12))} mm
                    </strong>
                </div>

            </div>

            <div class="prob">
                Prob. máx. 6h:
                {fmt(prob.get(6),0)}%
            </div>
        </div>
        """

    alerta = ""

    if (
        modelo
        and modelo[
            "aceleracao"
        ] > 0.05
    ):

        alerta += """
        <div class="alerta">
            ⚠ Subida acelerando em Santa Tereza.
        </div>
        """

    if (
        v_jose is not None
        and v_jose > 0.80
    ):

        alerta += """
        <div class="alerta">
            ⚠ Linha José Júlio apresenta subida forte.
        </div>
        """

    barragens_html = gerar_barragens_html(
        barragens
    )

    atualizado = datetime.now().strftime(
        "%d/%m/%Y %H:%M:%S"
    )

    html = f"""
<!DOCTYPE html>

<html lang="pt-BR">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<meta
    http-equiv="refresh"
    content="60"
>

<title>
Monitor Taquari V3
</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: #0b1115;
    color: #eef4f7;
    font-family:
        Segoe UI,
        Arial,
        sans-serif;
}}

header {{
    padding: 24px 32px;
    background: #131b21;
    border-bottom: 1px solid #29343b;
}}

h1 {{
    margin: 0;
    font-size: 25px;
}}

.atualizado {{
    color: #8899a5;
    margin-top: 6px;
}}

main {{
    max-width: 1500px;
    margin: auto;
    padding: 28px;
}}

.grid {{
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(300px,1fr)
        );
    gap: 18px;
}}

.card {{
    background: #151d23;
    border: 1px solid #29363e;
    border-radius: 14px;
    padding: 20px;
}}

.titulo {{
    color: #899ba6;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .5px;
}}

.nivel {{
    font-size: 48px;
    font-weight: 750;
    margin-top: 10px;
}}

.seta {{
    font-size: 32px;
}}

.hora {{
    color: #93a1aa;
    margin-top: 4px;
}}

.status {{
    margin-top: 12px;
    font-weight: 700;
}}

.metricas {{
    display: grid;
    grid-template-columns:
        repeat(3,1fr);
    gap: 9px;
    margin-top: 18px;
}}

.metricas div,
.chuva-grid div {{
    background: #0d1418;
    border-radius: 8px;
    padding: 11px;
}}

span {{
    display: block;
    color: #7e909b;
    font-size: 11px;
}}

strong {{
    display: block;
    margin-top: 5px;
}}

.previsoes {{
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px,1fr)
        );
    gap: 10px;
    margin-top: 16px;
}}

.previsao-item {{
    background: #0d1418;
    padding: 14px;
    border-radius: 9px;
}}

.previsao-item strong {{
    font-size: 23px;
}}

.previsao-item small {{
    color: #83939d;
    display: block;
    margin-top: 7px;
}}

.chuva-grid {{
    display: grid;
    grid-template-columns:
        repeat(2,1fr);
    gap: 9px;
    margin-top: 15px;
}}

.prob {{
    color: #899ba5;
    margin-top: 13px;
}}

.alerta {{
    margin-top: 14px;
    background: #352812;
    border-left: 4px solid #e0a33d;
    padding: 13px;
    border-radius: 5px;
}}

.secao {{
    margin-top: 26px;
}}

.aviso {{
    margin-top: 25px;
    padding: 15px;
    background: #1c2124;
    border-left: 4px solid #667783;
    color: #aab5bc;
}}

@media(max-width:700px) {{

    .metricas {{
        grid-template-columns: 1fr;
    }}

}}

</style>

</head>

<body>

<header>

<h1>
Monitor Hidrológico — Rio Taquari
</h1>

<div class="atualizado">
V3 · atualizado {atualizado}
</div>

</header>

<main>

<div class="grid">

<div class="card">

<div class="titulo">
SANTA TEREZA
</div>

<div class="nivel">
{
    fmt(
        santa_atual["nivel_m"]
        if santa_atual
        else None
    )
} m
<span class="seta">
{seta(v_santa)}
</span>
</div>

<div class="hora">
{
    santa_atual["data_hora"].strftime(
        "%d/%m/%Y %H:%M"
    )
    if santa_atual
    else "-"
}
</div>

<div class="status">
{st_status}
· dado há {fmt(st_idade,0)} min
</div>

<div class="metricas">

<div>
<span>30 min</span>
<strong>
{fmt(
    velocidade_janela(
        santa,
        30
    )
)} m/h
</strong>
</div>

<div>
<span>1 hora</span>
<strong>
{fmt(v_santa)} m/h
</strong>
</div>

<div>
<span>2 horas</span>
<strong>
{fmt(
    velocidade_janela(
        santa,
        120
    )
)} m/h
</strong>
</div>

</div>

</div>


<div class="card">

<div class="titulo">
LINHA JOSÉ JÚLIO
</div>

<div class="nivel">
{
    fmt(
        jose_atual["nivel_m"]
        if jose_atual
        else None
    )
} m
<span class="seta">
{seta(v_jose)}
</span>
</div>

<div class="hora">
{
    jose_atual["data_hora"].strftime(
        "%d/%m/%Y %H:%M"
    )
    if jose_atual
    else "-"
}
</div>

<div class="status">
{jj_status}
· dado há {fmt(jj_idade,0)} min
</div>

<div class="metricas">

<div>
<span>Subida 1h</span>
<strong>
{fmt(v_jose)} m/h
</strong>
</div>

<div>
<span>Vazão</span>
<strong>
{
    fmt(
        jose_atual["vazao"],
        0
    )
    if (
        jose_atual
        and jose_atual[
            "vazao"
        ] is not None
    )
    else "-"
} m³/s
</strong>
</div>

<div>
<span>Chuva estação</span>
<strong>
{
    fmt(
        jose_atual["chuva"]
    )
    if (
        jose_atual
        and jose_atual[
            "chuva"
        ] is not None
    )
    else "-"
} mm
</strong>
</div>

</div>

</div>

</div>


{alerta}


<div class="secao card">

<div class="titulo">
ESTIMATIVA EXPERIMENTAL — SANTA TEREZA
</div>

<div class="previsoes">

{previsao_html}

</div>

</div>


{barragens_html}

<div class="secao grid">

{meteo_html}

</div>


<div class="aviso">

As projeções são experimentais e não substituem
alertas oficiais. A faixa aumenta conforme o horizonte
porque a incerteza hidrológica também aumenta.
A influência das estações a montante e das barragens
ainda será calibrada com dados observados.

</div>

</main>

</body>

</html>
"""

    html = ajustar_layout_status_servidor(html)
    ARQ_DASH.write_text(html,
        encoding="utf-8"
    )


# ============================================================
# STATUS JSON
# ============================================================

def salvar_status(
    por_estacao,
    modelo,
):

    saida = {
        "atualizado_em":
            datetime.now().isoformat(),

        "proxima_coleta":
            (
                datetime.now()
                + timedelta(
                    seconds=INTERVALO
                )
            ).isoformat(),

        "estacoes": {},
    }

    for nome, dados in (
        por_estacao.items()
    ):

        if not dados:
            continue

        ultimo = dados[-1]

        status, idade = status_fonte(
            ultimo["data_hora"]
        )

        saida[
            "estacoes"
        ][nome] = {
            "data_hora":
                ultimo[
                    "data_hora"
                ].isoformat(),

            "nivel_m":
                ultimo[
                    "nivel_m"
                ],

            "vazao":
                ultimo[
                    "vazao"
                ],

            "status":
                status,

            "idade_min":
                idade,
        }

    if modelo:

        saida[
            "previsao"
        ] = {
            str(h): p
            for h, p
            in modelo[
                "previsoes"
            ].items()
        }

    ARQ_STATUS.write_text(
        json.dumps(
            saida,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )



# ============================================================
# RESUMO WHATSAPP
# ============================================================

def formatar_inteiro_br(
    valor,
):

    if valor is None:
        return "-"

    try:

        valor = int(
            round(
                float(valor)
            )
        )

        return (
            f"{valor:,}"
            .replace(
                ",",
                "."
            )
        )

    except Exception:

        return "-"


def montar_resumo_whatsapp(
    por_estacao,
    modelo,
    barragens,
):

    santa = por_estacao.get(
        "Santa Tereza",
        []
    )

    jose = por_estacao.get(
        "Linha Jose Julio",
        []
    )

    santa_atual = (
        santa[-1]
        if santa
        else None
    )

    jose_atual = (
        jose[-1]
        if jose
        else None
    )

    v_santa = (
        velocidade_janela(
            santa,
            60
        )
        if santa
        else None
    )

    v_jose = (
        velocidade_janela(
            jose,
            60
        )
        if jose
        else None
    )

    agora = datetime.now()

    linhas = [
        (
            "RIO TAQUARI — "
            + agora.strftime(
                "%d/%m %H:%M"
            )
        )
    ]

    if santa_atual:

        linhas.append(
            "Santa Tereza: "
            + fmt(
                santa_atual[
                    "nivel_m"
                ]
            )
            + " m "
            + seta(
                v_santa
            )
        )

    if jose_atual:

        linhas.append(
            "Linha Jose Julio: "
            + fmt(
                jose_atual[
                    "nivel_m"
                ]
            )
            + " m "
            + seta(
                v_jose
            )
        )

    if barragens:

        linhas.append("")
        linhas.append(
            "Barragens"
        )

        for b in barragens:

            linhas.append(
                (
                    b.get(
                        "nome",
                        "-"
                    )
                    + ": "
                    + formatar_inteiro_br(
                        b.get(
                            "sai"
                        )
                    )
                    + " m3/s "
                    + b.get(
                        "seta",
                        "="
                    )
                )
            )

    if modelo:

        p1 = modelo[
            "previsoes"
        ].get(
            1
        )

        p3 = modelo[
            "previsoes"
        ].get(
            3
        )

        linhas.append("")

        if p1:

            linhas.append(
                "Prev. ST +1h: "
                + fmt(
                    p1[
                        "estimado"
                    ]
                )
                + " m"
            )

        if p3:

            linhas.append(
                "Prev. ST +3h: "
                + fmt(
                    p3[
                        "estimado"
                    ]
                )
                + " m"
            )

    alertas = []

    if (
        modelo
        and modelo.get(
            "aceleracao",
            0
        ) > 0.05
    ):

        alertas.append(
            "Subida acelerando em Santa Tereza"
        )

    if (
        v_jose is not None
        and v_jose > 0.80
    ):

        alertas.append(
            "Linha Jose Julio com subida forte"
        )

    barragens_subindo = [
        b.get(
            "nome"
        )
        for b in (
            barragens or []
        )
        if b.get(
            "seta"
        ) == "↑"
    ]

    if barragens_subindo:

        alertas.append(
            "Vazoes das barragens aumentando"
        )

    for alerta in alertas[:2]:

        linhas.append(
            "⚠ "
            + alerta
        )

    proxima = (
        agora
        + timedelta(
            hours=1
        )
    )

    proxima = proxima.replace(
        minute=0,
        second=0,
        microsecond=0
    )

    linhas.append(
        ""
    )

    linhas.append(
        "Proxima atualizacao: "
        + proxima.strftime(
            "%H:%M"
        )
    )

    return "\n".join(
        linhas
    )


# ============================================================
# CONTROLE DE ENVIO HORARIO
# ============================================================

def carregar_estado_whatsapp():

    if not ARQ_WHATSAPP_ESTADO.exists():

        return {}

    try:

        return json.loads(
            ARQ_WHATSAPP_ESTADO.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return {}


def salvar_estado_whatsapp(
    estado,
):

    ARQ_WHATSAPP_ESTADO.write_text(
        json.dumps(
            estado,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def whatsapp_deve_enviar(
    por_estacao,
):

    agora = datetime.now()

    santa = por_estacao.get(
        "Santa Tereza",
        []
    )

    if not santa:

        return False

    ultima_leitura = santa[-1][
        "data_hora"
    ]

    leitura_chave = ultima_leitura.strftime(
        "%Y-%m-%d %H:%M"
    )

    estado = carregar_estado_whatsapp()

    # ========================================================
    # ENVIO FORCADO
    #
    # Usado quando o horario limite ja passou mas o primeiro
    # envio ainda nao ocorreu.
    # ========================================================

    if (
        estado.get("forcar_primeiro_envio")
        and not estado.get(
            "primeiro_envio_realizado",
            False
        )
    ):

        log(
            "WhatsApp: primeiro envio pendente. "
            "Envio liberado neste ciclo."
        )

        return True

    # ========================================================
    # PRIMEIRA EXECUCAO
    #
    # A leitura existente neste momento vira a referencia.
    # ========================================================

    if not estado.get(
        "leitura_referencia_inicial"
    ):

        estado[
            "leitura_referencia_inicial"
        ] = leitura_chave

        estado[
            "ultima_leitura_vista"
        ] = leitura_chave

        estado[
            "primeiro_envio_realizado"
        ] = False

        estado[
            "iniciado_em"
        ] = agora.isoformat()

        salvar_estado_whatsapp(
            estado
        )

        log(
            "WhatsApp: referencia ANA registrada em "
            f"{leitura_chave}. "
            "Aguardando nova leitura ou 23:45."
        )

        return False

    # ========================================================
    # PRIMEIRO ENVIO
    #
    # REGRA:
    #
    # 1) nova leitura da ANA
    # OU
    # 2) chegou 23:45
    #
    # O que acontecer primeiro.
    # ========================================================

    if not estado.get(
        "primeiro_envio_realizado",
        False
    ):

        referencia = estado.get(
            "leitura_referencia_inicial"
        )

        # ----------------------------------------------------
        # NOVA LEITURA ANA
        # ----------------------------------------------------

        if leitura_chave != referencia:

            log(
                "WhatsApp: NOVA LEITURA ANA detectada "
                f"({leitura_chave}). "
                "Primeiro envio liberado."
            )

            return True

        # ----------------------------------------------------
        # HORARIO LIMITE 23:45
        # ----------------------------------------------------

        horario_limite = agora.replace(
            hour=23,
            minute=45,
            second=0,
            microsecond=0
        )

        if agora >= horario_limite:

            log(
                "WhatsApp: horario limite 23:45 atingido. "
                "Primeiro envio liberado."
            )

            return True

        # ----------------------------------------------------
        # CONTINUA AGUARDANDO
        # ----------------------------------------------------

        minutos_restantes = (
            horario_limite - agora
        ).total_seconds() / 60

        log(
            "WhatsApp: aguardando nova leitura ANA "
            "ou 23:45. "
            f"Faltam aproximadamente "
            f"{max(0, minutos_restantes):.0f} min."
        )

        return False

    # ========================================================
    # DEPOIS DO PRIMEIRO ENVIO
    #
    # INTERVALO MINIMO DE 60 MINUTOS
    # ========================================================

    ultimo_envio = estado.get(
        "ultimo_envio_em"
    )

    if not ultimo_envio:

        return True

    try:

        dt_ultimo = datetime.fromisoformat(
            ultimo_envio
        )

    except Exception:

        return True

    minutos = (
        agora - dt_ultimo
    ).total_seconds() / 60

    if minutos >= 60:

        log(
            "WhatsApp: passaram "
            f"{minutos:.0f} minutos "
            "desde o ultimo envio."
        )

        return True

    return False

def processar_whatsapp(
    por_estacao,
    modelo,
    barragens,
):

    if not whatsapp_deve_enviar(por_estacao):

        return

    agora = datetime.now()

    mensagem = montar_resumo_whatsapp(
        por_estacao,
        modelo,
        barragens
    )

    log(
        "Preparando resumo WhatsApp..."
    )

    try:

        resultados = enviar_mensagens(
            DESTINATARIOS_WHATSAPP,
            mensagem
        )

        sucessos = [
            r
            for r in resultados
            if r.get(
                "ok"
            )
        ]

        if sucessos:

            estado = carregar_estado_whatsapp()

            estado[
                "ultima_hora_enviada"
            ] = agora.strftime(
                "%Y-%m-%d %H"
            )

            estado[
                "ultimo_envio_em"
            ] = agora.isoformat()

            estado[
                "primeiro_envio_realizado"
            ] = True

            estado[
                "forcar_primeiro_envio"
            ] = False

            estado[
                "ultima_mensagem"
            ] = mensagem

            santa_atual = por_estacao.get(
                "Santa Tereza",
                []
            )

            if santa_atual:

                estado[
                    "ultima_leitura_enviada"
                ] = santa_atual[-1][
                    "data_hora"
                ].strftime(
                    "%Y-%m-%d %H:%M"
                )

            salvar_estado_whatsapp(
                estado
            )

            log(
                "WhatsApp enviado para "
                + str(
                    len(
                        sucessos
                    )
                )
                + " destinatario(s)."
            )

        else:

            log(
                "WhatsApp nao foi enviado."
            )

    except Exception as e:

        log(
            f"ERRO WHATSAPP: {e}"
        )

# ============================================================
# CICLO
# ============================================================

def ajustar_layout_status_servidor(html):

    if not html:
        return html

    css = """
    <style>
    .topbar-monitor{
        display:flex;
        justify-content:space-between;
        align-items:flex-start;
        gap:18px;
        flex-wrap:wrap;
    }

    .topbar-monitor-esq{
        flex:1 1 520px;
        min-width:0;
    }

    .topbar-monitor-dir{
        flex:0 1 340px;
        width:min(340px, 100%);
        margin-left:auto;
    }

    .status-servidor-inline{
        position:static !important;
        inset:auto !important;
        right:auto !important;
        left:auto !important;
        top:auto !important;
        bottom:auto !important;
        margin:0 !important;
        width:100% !important;
        max-width:100% !important;
        z-index:1 !important;
    }

    @media (max-width: 768px){
        .topbar-monitor{
            flex-direction:column;
            align-items:stretch;
        }

        .topbar-monitor-dir{
            width:100%;
            margin-left:0;
        }
    }
    </style>
    """

    js = r"""
    <script>
    (function () {
        function moverStatusServidor() {
            var titulo = Array.from(document.querySelectorAll("h1")).find(function (el) {
                return (el.textContent || "").indexOf("Monitor Hidrológico") >= 0;
            });

            if (!titulo) return;

            var marcador = Array.from(document.querySelectorAll("div,span,strong,b")).find(function (el) {
                return (el.textContent || "").trim() === "Status do servidor";
            });

            if (!marcador) return;

            var box = marcador;

            while (box.parentElement && box.parentElement.tagName && box.parentElement.tagName.toLowerCase() === "div") {
                var pai = box.parentElement;
                var textoPai = (pai.textContent || "");
                if (textoPai.indexOf("Status do servidor") >= 0 && pai.children.length >= 1) {
                    box = pai;
                } else {
                    break;
                }
            }

            var blocoTitulo = titulo.closest("div");
            if (!blocoTitulo) return;

            var blocoSubtitulo = blocoTitulo.nextElementSibling;

            if (!document.getElementById("slot-status-servidor")) {
                var topo = document.createElement("div");
                topo.className = "topbar-monitor";

                var esq = document.createElement("div");
                esq.className = "topbar-monitor-esq";

                var dir = document.createElement("div");
                dir.className = "topbar-monitor-dir";
                dir.id = "slot-status-servidor";

                blocoTitulo.parentNode.insertBefore(topo, blocoTitulo);
                topo.appendChild(esq);
                topo.appendChild(dir);

                esq.appendChild(blocoTitulo);

                if (blocoSubtitulo) {
                    esq.appendChild(blocoSubtitulo);
                }
            }

            var slot = document.getElementById("slot-status-servidor");
            if (!slot) return;

            box.classList.add("status-servidor-inline");
            slot.innerHTML = "";
            slot.appendChild(box);
        }

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", moverStatusServidor);
        } else {
            moverStatusServidor();
        }
    })();
    </script>
    """

    if "topbar-monitor" not in html:
        html = html.replace("</head>", css + "\n</head>")

    if "slot-status-servidor" not in html:
        html = html.replace("</body>", js + "\n</body>")

    return html

def ciclo():

    log(
        "=" * 55
    )

    log(
        "Nova coleta V3"
    )

    recebidos = []

    por_estacao = {}

    for nome, cfg in (
        ESTACOES.items()
    ):

        try:

            dados = buscar_ana(
                nome,
                cfg["codigo"]
            )

            por_estacao[
                nome
            ] = dados

            recebidos.extend(
                dados
            )

            if dados:

                ultimo = dados[-1]

                status, idade = (
                    status_fonte(
                        ultimo[
                            "data_hora"
                        ]
                    )
                )

                log(
                    f"{nome}: "
                    f'{ultimo["nivel_m"]:.2f} m '
                    f"| {status} "
                    f"| {idade:.0f} min"
                )

        except Exception as e:

            log(
                f"ERRO ANA {nome}: {e}"
            )

            por_estacao[
                nome
            ] = []

    if recebidos:

        salvar_historico(
            recebidos
        )

    santa = por_estacao.get(
        "Santa Tereza",
        []
    )

    jose = por_estacao.get(
        "Linha Jose Julio",
        []
    )

    modelo = prever_santa(
        santa,
        jose
    )

    if modelo:

        log(
            "Velocidade ST 1h: "
            + f'{modelo["v60"]:+.2f} m/h'
            if modelo[
                "v60"
            ] is not None
            else "Velocidade ST indisponivel"
        )

        for h in [
            1,
            2,
            3,
            6,
        ]:

            p = modelo[
                "previsoes"
            ][h]

            log(
                f"Previsao +{h}h: "
                f'{p["estimado"]:.2f} m '
                f'({p["min"]:.2f} - '
                f'{p["max"]:.2f})'
            )

    try:

        barragens = coletar_barragens()

        for b in barragens:

            log(
                f'Barragem {b["nome"]}: '
                f'{b["sai"] if b["sai"] is not None else "-"} '
                f'm3/s {b.get("seta","=")}'
            )

    except Exception as e:

        log(
            f"ERRO BARRAGENS: {e}"
        )

        barragens = []

    meteo = coletar_meteorologia()

    gerar_dashboard(
        por_estacao,
        modelo,
        meteo,
        barragens
    )

    # ========================================================
    # WHATSAPP AUTOMATICO
    # ========================================================

    salvar_status(
        por_estacao,
        modelo
    )

    log(
        "Dashboard V3 atualizado."
    )



def abrir_chrome(caminho_html):

    caminho_html = Path(caminho_html).resolve()

    chrome_candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(
            Path(
                os.environ.get(
                    "LOCALAPPDATA",
                    ""
                )
            )
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe"
        ),
    ]

    for chrome in chrome_candidatos:

        if chrome and os.path.exists(chrome):

            try:

                import subprocess

                subprocess.Popen(
                    [
                        chrome,
                        str(caminho_html),
                    ]
                )

                return True

            except Exception:
                pass

    try:

        webbrowser.open(
            caminho_html.as_uri()
        )

        return True

    except Exception:

        return False

# ============================================================
# MAIN
# ============================================================

def main():

    preparar()

    log(
        "MONITOR TAQUARI V3 INICIADO"
    )

    log(
        "Coleta automatica: 5 minutos"
    )

    primeira = True

    while True:

        inicio = time.time()

        try:

            ciclo()

        except KeyboardInterrupt:

            log(
                "Monitor encerrado."
            )

            break

        except Exception:

            log(
                traceback.format_exc()
            )

        if primeira:

            primeira = False

            try:

                abrir_chrome(ARQ_DASH)

            except Exception:
                pass

        duracao = (
            time.time()
            - inicio
        )

        espera = max(
            5,
            INTERVALO - duracao
        )

        proxima = (
            datetime.now()
            + timedelta(
                seconds=espera
            )
        )

        log(
            "Proxima coleta: "
            + proxima.strftime(
                "%H:%M:%S"
            )
        )

        time.sleep(
            espera
        )





