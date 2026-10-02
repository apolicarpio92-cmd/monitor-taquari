from __future__ import annotations

import csv
import json
import math
import os
import queue
import statistics
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import requests


from barragens import coletar_barragens
from barragens_historico_web import (
    atualizar_historico_barragens,
)

from cameras_vale_vivo import coletar_cameras_vale_vivo
from satelite_copernicus import (
    coletar_imagens_atuais,
)


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

# Timeout exclusivo para ANA:
# 5 s para conexao e 12 s para leitura.
# Evita uma requisicao ANA prender o ciclo inteiro.
TIMEOUT_ANA = (5, 12)

ETAPA_CICLO = "aguardando"
ETAPA_CICLO_EM = None


def marcar_etapa(nome):

    global ETAPA_CICLO
    global ETAPA_CICLO_EM

    ETAPA_CICLO = str(nome)

    ETAPA_CICLO_EM = datetime.now().isoformat(
        timespec="seconds"
    )

    print(
        (
            "[CICLO-ETAPA] "
            + ETAPA_CICLO
            + " | "
            + ETAPA_CICLO_EM
        ),
        flush=True,
    )


_ANA_THREAD_ATIVA = None


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

def requisicao_ana_isolada(
    url,
    params,
):

    global _ANA_THREAD_ATIVA

    # --------------------------------------------------------
    # Se uma tentativa anterior ainda estiver bloqueada,
    # nao cria outra thread.
    # --------------------------------------------------------

    if (
        _ANA_THREAD_ATIVA is not None
        and _ANA_THREAD_ATIVA.is_alive()
    ):

        raise TimeoutError(
            (
                "Requisicao ANA anterior "
                "ainda esta bloqueada. "
                "Usando fallback local."
            )
        )

    resultado = queue.Queue(
        maxsize=1
    )

    def executar():

        try:

            resposta = requests.get(
                url,
                params=params,
                timeout=(4, 6),
                headers={
                    "User-Agent":
                        "Monitor-Taquari-V3/1.0"
                },
            )

            resposta.raise_for_status()

            if not resposta.content:

                raise RuntimeError(
                    "Resposta vazia da ANA"
                )

            resultado.put(
                (
                    "ok",
                    resposta,
                )
            )

        except Exception as e:

            try:

                resultado.put(
                    (
                        "erro",
                        (
                            type(e).__name__
                            + ": "
                            + str(e)
                        ),
                    )
                )

            except Exception:
                pass

    thread = threading.Thread(
        target=executar,
        daemon=True,
        name="monitor-ana-http",
    )

    _ANA_THREAD_ATIVA = thread

    inicio_http = time.monotonic()

    thread.start()

    # --------------------------------------------------------
    # Este timeout independe do requests.
    #
    # Mesmo que DNS/socket fique preso, o ciclo principal
    # volta depois de no maximo 12 segundos.
    # --------------------------------------------------------

    thread.join(
        timeout=12
    )

    duracao = (
        time.monotonic()
        - inicio_http
    )

    if thread.is_alive():

        raise TimeoutError(
            (
                "ANA excedeu timeout rigido "
                f"de 12s ({duracao:.1f}s). "
                "Thread abandonada; fallback local."
            )
        )

    try:

        status, payload = (
            resultado.get_nowait()
        )

    except queue.Empty:

        raise RuntimeError(
            (
                "Thread ANA terminou sem "
                "retornar resultado."
            )
        )

    if status != "ok":

        raise RuntimeError(
            str(payload)
        )

    return payload

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

            marcar_etapa(
                "ana_http_"
                + str(nome)
                + "_"
                + str(tipo_ana)
            )

            inicio_http = time.monotonic()

            resposta_teste = (
                requisicao_ana_isolada(
                    url_ana,
                    params,
                )
            )

            resposta_teste.raise_for_status()

            duracao_http = (
                time.monotonic()
                - inicio_http
            )

            log(
                (
                    f"ANA {nome} endpoint {tipo_ana}: "
                    f"HTTP {resposta_teste.status_code} "
                    f"em {duracao_http:.2f}s "
                    f"({len(resposta_teste.content)} bytes)"
                )
            )

            marcar_etapa(
                "ana_parse_"
                + str(nome)
                + "_"
                + str(tipo_ana)
            )

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

            marcar_etapa(
                "ana_falha_"
                + str(nome)
                + "_"
                + str(tipo_ana)
            )

            log(
                f"ANA {nome}: falha endpoint "
                f"{tipo_ana}: {type(e).__name__}: {e}"
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

def gerar_monitoramento_visual_html(
    cameras,
):

    import html as _html

    if not cameras:

        return """
        <div class="vv-sem-dados">
            Não foi possível consultar as câmeras
            neste momento.
        </div>
        """

    def esc(valor):

        return _html.escape(
            str(
                valor
                if valor is not None
                else ""
            ),
            quote=True,
        )

    # --------------------------------------------------------
    # Escolhe a primeira transmissão disponível.
    # Normalmente será Santa Tereza.
    # --------------------------------------------------------

    inicial = None

    for camera in cameras:

        if (
            camera.get("video_id")
            and camera.get("status")
            in (
                "ao_vivo",
                "disponivel",
            )
        ):

            inicial = camera
            break

    if inicial is None:

        inicial = cameras[0]

    botoes = []

    for camera in cameras:

        status = camera.get(
            "status",
            "indisponivel",
        )

        if status == "ao_vivo":

            classe_status = "online"
            bolinha = "●"

        elif status == "disponivel":

            classe_status = "disponivel"
            bolinha = "●"

        elif status == "desconectada":

            classe_status = "offline"
            bolinha = "○"

        else:

            classe_status = "offline"
            bolinha = "○"

        ativo = (
            " ativo"
            if camera["id"]
            == inicial["id"]
            else ""
        )

        botoes.append(
            f"""
            <button
                type="button"
                class="vv-botao-camera {classe_status}{ativo}"
                data-camera-id="{esc(camera['id'])}"
                data-video="{esc(camera.get('video_id') or '')}"
                data-status="{esc(status)}"
                data-nome="{esc(camera['nome'])}"
                data-titulo="{esc(camera['titulo'])}"
                data-descricao="{esc(camera['descricao'])}"
                data-pagina="{esc(camera['pagina'])}"
                onclick="selecionarCameraValeVivo(this)"
            >
                <span class="vv-botao-status">
                    {bolinha}
                </span>

                <span>
                    {esc(camera["nome"])}
                </span>
            </button>
            """
        )

    status_inicial = inicial.get(
        "status",
        "indisponivel",
    )

    video_inicial = inicial.get(
        "video_id"
    )

    disponivel_inicial = (
        bool(video_inicial)
        and status_inicial
        in (
            "ao_vivo",
            "disponivel",
        )
    )

    if status_inicial == "ao_vivo":

        texto_status = (
            "TRANSMISSÃO DISPONÍVEL"
        )

        classe_status = "online"

    elif status_inicial == "disponivel":

        texto_status = (
            "PLAYER DISPONÍVEL"
        )

        classe_status = "online"

    elif status_inicial == "desconectada":

        texto_status = (
            "CÂMERA DESCONECTADA"
        )

        classe_status = "offline"

    else:

        texto_status = (
            "TRANSMISSÃO INDISPONÍVEL"
        )

        classe_status = "offline"

    if disponivel_inicial:

        src_inicial = (
            "https://www.youtube.com/embed/"
            + esc(video_inicial)
            + "?autoplay=1&mute=1&rel=0"
        )

        iframe_src = (
            f'src="{src_inicial}"'
        )

        mensagem_display = "none"

    else:

        iframe_src = ""
        mensagem_display = "flex"

    html_base = f"""
    <div class="vv-monitor">

        <div class="vv-intro">

            <div>

                <div class="vv-titulo">
                    MONITORAMENTO VISUAL DO RIO TAQUARI
                </div>

                <div class="vv-subtitulo">
                    Câmeras públicas do Vale Vivo 24h,
                    organizadas no sentido do percurso do rio.
                </div>

            </div>

            <div
                id="vv-status-geral"
                class="vv-status {classe_status}"
            >
                <span>●</span>
                <span id="vv-status-texto">
                    {texto_status}
                </span>
            </div>

        </div>


        <div class="vv-navegacao">

            {''.join(botoes)}

        </div>


        <div class="vv-player-card">

            <div class="vv-player-topo">

                <div>

                    <div
                        id="vv-camera-nome"
                        class="vv-local"
                    >
                        {esc(inicial["nome"])}
                    </div>

                    <div
                        id="vv-camera-titulo"
                        class="vv-local-titulo"
                    >
                        {esc(inicial["titulo"])}
                    </div>

                    <div
                        id="vv-camera-descricao"
                        class="vv-local-descricao"
                    >
                        {esc(inicial["descricao"])}
                    </div>

                </div>

                <div class="vv-fonte">
                    Fonte: Vale Vivo 24h
                </div>

            </div>


            <div class="vv-video-wrap">

                <iframe
                    id="vv-camera-frame"
                    {iframe_src}
                    title="Câmera Vale Vivo"
                    allow="
                        accelerometer;
                        autoplay;
                        clipboard-write;
                        encrypted-media;
                        gyroscope;
                        picture-in-picture;
                        web-share
                    "
                    referrerpolicy="
                        strict-origin-when-cross-origin
                    "
                    allowfullscreen
                ></iframe>

                <div
                    id="vv-camera-indisponivel"
                    class="vv-indisponivel"
                    style="display:{mensagem_display};"
                >
                    <div>

                        <strong>
                            Transmissão temporariamente
                            indisponível
                        </strong>

                        <span>
                            A fonte pública não está transmitindo
                            este ponto neste momento.
                        </span>

                    </div>
                </div>

            </div>


            <div class="vv-rodape">

                <div>
                    A imagem é fornecida por uma câmera pública
                    externa. A disponibilidade depende do
                    serviço Vale Vivo.
                </div>

                <a
                    id="vv-link-fonte"
                    href="{esc(inicial['pagina'])}"
                    target="_blank"
                    rel="noopener noreferrer"
                >
                    ABRIR NA FONTE
                </a>

            </div>

        </div>

    </div>
    """

    javascript = """
    <script>
    function selecionarCameraValeVivo(botao) {

        var botoes = document.querySelectorAll(
            ".vv-botao-camera"
        );

        botoes.forEach(function(item) {
            item.classList.remove("ativo");
        });

        botao.classList.add("ativo");

        var video = (
            botao.getAttribute("data-video")
            || ""
        );

        var status = (
            botao.getAttribute("data-status")
            || "indisponivel"
        );

        var nome = (
            botao.getAttribute("data-nome")
            || ""
        );

        var titulo = (
            botao.getAttribute("data-titulo")
            || ""
        );

        var descricao = (
            botao.getAttribute("data-descricao")
            || ""
        );

        var pagina = (
            botao.getAttribute("data-pagina")
            || "#"
        );

        var frame = document.getElementById(
            "vv-camera-frame"
        );

        var indisponivel = document.getElementById(
            "vv-camera-indisponivel"
        );

        var statusGeral = document.getElementById(
            "vv-status-geral"
        );

        var statusTexto = document.getElementById(
            "vv-status-texto"
        );

        document.getElementById(
            "vv-camera-nome"
        ).textContent = nome;

        document.getElementById(
            "vv-camera-titulo"
        ).textContent = titulo;

        document.getElementById(
            "vv-camera-descricao"
        ).textContent = descricao;

        document.getElementById(
            "vv-link-fonte"
        ).href = pagina;

        statusGeral.classList.remove(
            "online",
            "offline"
        );

        var podeExibir = (
            video
            && (
                status === "ao_vivo"
                || status === "disponivel"
            )
        );

        if (podeExibir) {

            statusGeral.classList.add(
                "online"
            );

            if (status === "ao_vivo") {
                statusTexto.textContent =
                    "TRANSMISSÃO DISPONÍVEL";
            } else {
                statusTexto.textContent =
                    "PLAYER DISPONÍVEL";
            }

            indisponivel.style.display =
                "none";

            var novaUrl =
                "https://www.youtube.com/embed/"
                + video
                + "?autoplay=1&mute=1&rel=0";

            if (
                frame.getAttribute("src")
                !== novaUrl
            ) {
                frame.setAttribute(
                    "src",
                    novaUrl
                );
            }

        } else {

            statusGeral.classList.add(
                "offline"
            );

            if (
                status
                === "desconectada"
            ) {
                statusTexto.textContent =
                    "CÂMERA DESCONECTADA";
            } else {
                statusTexto.textContent =
                    "TRANSMISSÃO INDISPONÍVEL";
            }

            frame.removeAttribute(
                "src"
            );

            indisponivel.style.display =
                "flex";
        }
    }
    </script>
    """

    return (
        html_base
        + javascript
    )


def gerar_comparativo_satelite_html(
    imagens,
):

    ordem = [
        "Cabeceiras / Vacaria",
        "Barra Mansa",
        "Santa Tereza",
    ]

    blocos = []

    for nome in ordem:

        atual = imagens.get(
            nome,
            {},
        )

        if not atual.get("ok"):

            blocos.append(
                f"""
                <div class="card comparativo-card">

                    <div class="titulo">
                        {nome.upper()}
                    </div>

                    <div class="comparativo-sem-dados">
                        Dados de satélite indisponíveis.
                    </div>

                </div>
                """
            )

            continue

        anterior = atual.get(
            "anterior"
        )

        if not anterior:

            blocos.append(
                f"""
                <div class="card comparativo-card">

                    <div class="titulo">
                        {nome.upper()}
                    </div>

                    <div class="comparativo-sem-dados">
                        Não foi encontrada uma cena anterior
                        adequada para comparação.
                    </div>

                </div>
                """
            )

            continue

        data_atual = atual.get(
            "data"
        )

        data_anterior = anterior.get(
            "data"
        )

        data_atual_txt = (
            data_atual.astimezone().strftime(
                "%d/%m/%Y %H:%M"
            )
            if data_atual
            else "-"
        )

        data_anterior_txt = (
            data_anterior.astimezone().strftime(
                "%d/%m/%Y %H:%M"
            )
            if data_anterior
            else "-"
        )

        nuvens_atual = atual.get(
            "nuvens"
        )

        nuvens_anterior = anterior.get(
            "nuvens"
        )

        nuvens_atual_txt = (
            f"{nuvens_atual:.1f}%"
            if nuvens_atual is not None
            else "-"
        )

        nuvens_anterior_txt = (
            f"{nuvens_anterior:.1f}%"
            if nuvens_anterior is not None
            else "-"
        )

        thumb_atual = atual.get(
            "thumbnail"
        )

        thumb_anterior = anterior.get(
            "thumbnail"
        )

        sat_atual = atual.get(
            "satellite",
            "Sentinel-2",
        )

        sat_anterior = anterior.get(
            "satellite",
            "Sentinel-2",
        )

        imagem_atual_html = (
            f"""
            <img
                src="{thumb_atual}"
                class="comparativo-img"
                alt="Cena atual de {nome}"
                loading="lazy"
            >
            """
            if thumb_atual
            else """
            <div class="comparativo-img-vazia">
                Imagem indisponível
            </div>
            """
        )

        imagem_anterior_html = (
            f"""
            <img
                src="{thumb_anterior}"
                class="comparativo-img"
                alt="Cena anterior de {nome}"
                loading="lazy"
            >
            """
            if thumb_anterior
            else """
            <div class="comparativo-img-vazia">
                Imagem indisponível
            </div>
            """
        )

        intervalo_txt = "-"

        if (
            data_atual
            and data_anterior
        ):

            intervalo = (
                data_atual
                - data_anterior
            )

            dias = (
                intervalo.days
            )

            if dias == 0:
                intervalo_txt = "< 1 dia"

            elif dias == 1:
                intervalo_txt = "1 dia"

            else:
                intervalo_txt = (
                    f"{dias} dias"
                )

        blocos.append(
            f"""
            <div class="card comparativo-card">

                <div class="comparativo-topo">

                    <div class="titulo">
                        {nome.upper()}
                    </div>

                    <div class="comparativo-intervalo">
                        INTERVALO · {intervalo_txt}
                    </div>

                </div>

                <div class="comparativo-dupla">

                    <div class="comparativo-cena">

                        <div class="comparativo-rotulo anterior">
                            ANTERIOR
                        </div>

                        <div class="comparativo-imagem-wrap">
                            {imagem_anterior_html}
                        </div>

                        <div class="comparativo-meta">

                            <div>
                                <span>Data</span>
                                <strong>
                                    {data_anterior_txt}
                                </strong>
                            </div>

                            <div>
                                <span>Nuvens</span>
                                <strong>
                                    {nuvens_anterior_txt}
                                </strong>
                            </div>

                            <div>
                                <span>Satélite</span>
                                <strong>
                                    {sat_anterior}
                                </strong>
                            </div>

                        </div>

                    </div>


                    <div class="comparativo-cena">

                        <div class="comparativo-rotulo atual">
                            MAIS RECENTE
                        </div>

                        <div class="comparativo-imagem-wrap">
                            {imagem_atual_html}
                        </div>

                        <div class="comparativo-meta">

                            <div>
                                <span>Data</span>
                                <strong>
                                    {data_atual_txt}
                                </strong>
                            </div>

                            <div>
                                <span>Nuvens</span>
                                <strong>
                                    {nuvens_atual_txt}
                                </strong>
                            </div>

                            <div>
                                <span>Satélite</span>
                                <strong>
                                    {sat_atual}
                                </strong>
                            </div>

                        </div>

                    </div>

                </div>

                <div class="comparativo-aviso">
                    Comparação visual entre duas cenas reais.
                    Diferenças aparentes também podem resultar
                    de iluminação, nuvens, vegetação e condições
                    atmosféricas.
                </div>

            </div>
            """
        )

    return (
        """
        <div class="comparativo-lista">
        """
        + "".join(
            blocos
        )
        + """
        </div>
        """
    )


def gerar_imagens_satelite_html(
    imagens,
):

    cards = []

    ordem = [
        "Cabeceiras / Vacaria",
        "Barra Mansa",
        "Santa Tereza",
    ]

    for nome in ordem:

        d = imagens.get(
            nome,
            {},
        )

        if not d.get("ok"):

            cards.append(
                f"""
                <div class="card sat-card">

                    <div class="titulo">
                        {nome.upper()}
                    </div>

                    <div class="sat-sem-dados">
                        Imagem indisponível.
                    </div>

                </div>
                """
            )

            continue

        data = d.get(
            "data"
        )

        if data:

            data_txt = data.astimezone().strftime(
                "%d/%m/%Y %H:%M"
            )

        else:

            data_txt = "-"

        nuvens = d.get(
            "nuvens"
        )

        if nuvens is not None:

            nuvens_txt = (
                f"{nuvens:.1f}%"
            )

        else:

            nuvens_txt = "-"

        satelite = d.get(
            "satellite",
            "Sentinel-2",
        )

        idade_dias = d.get(
            "idade_dias"
        )

        idade_status = d.get(
            "idade_status",
            "SEM DATA",
        )

        idade_classe = d.get(
            "idade_classe",
            "neutro",
        )

        nuvem_status = d.get(
            "nuvem_status",
            "NUVENS DESCONHECIDAS",
        )

        nuvem_classe = d.get(
            "nuvem_classe",
            "neutro",
        )

        if idade_dias is None:

            idade_txt = "-"

        elif idade_dias == 0:

            idade_txt = "hoje"

        elif idade_dias == 1:

            idade_txt = "1 dia"

        else:

            idade_txt = (
                f"{idade_dias} dias"
            )

        thumbnail = d.get(
            "thumbnail"
        )

        imagem_html = ""

        if thumbnail:

            imagem_html = f"""
            <div class="sat-imagem-wrap">

                <img
                    src="{thumbnail}"
                    alt="Imagem de satélite de {nome}"
                    class="sat-imagem"
                    loading="lazy"
                >

            </div>
            """

        else:

            imagem_html = """
            <div class="sat-imagem-vazia">
                Prévia indisponível
            </div>
            """

        cards.append(
            f"""
            <div class="card sat-card">

                <div class="sat-cabecalho">

                    <div class="titulo">
                        {nome.upper()}
                    </div>

                    <div class="sat-badges">

                        <span
                            class="sat-badge {idade_classe}"
                        >
                            {idade_status}
                        </span>

                        <span
                            class="sat-badge {nuvem_classe}"
                        >
                            {nuvem_status}
                        </span>

                    </div>

                </div>

                {imagem_html}

                <div class="sat-meta">

                    <div>
                        <span>Satélite</span>
                        <strong>
                            {satelite}
                        </strong>
                    </div>

                    <div>
                        <span>Última cena útil</span>
                        <strong>
                            {data_txt}
                        </strong>
                    </div>

                    <div>
                        <span>Nuvens na cena</span>
                        <strong>
                            {nuvens_txt}
                        </strong>
                    </div>

                    <div>
                        <span>Idade da imagem</span>
                        <strong>
                            {idade_txt}
                        </strong>
                    </div>

                </div>

                <div class="sat-aviso">
                    Cena selecionada priorizando baixa
                    nebulosidade e recência.
                    Imagem real de satélite;
                    não representa transmissão ao vivo.
                </div>

            </div>
            """
        )

    return (
        """
        <div class="sat-grid">
        """
        + "".join(cards)
        + """
        </div>
        """
    )


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

    try:

        imagens_satelite = (
            coletar_imagens_atuais()
        )

    except Exception:

        imagens_satelite = {}

    imagens_satelite_html = (
        gerar_imagens_satelite_html(
            imagens_satelite
        )
    )

    comparativo_satelite_html = (
        gerar_comparativo_satelite_html(
            imagens_satelite
        )
    )

    try:

        cameras_vale_vivo = (
            coletar_cameras_vale_vivo()
        )

    except Exception as exc:

        print(
            "[CAMERAS] Falha Vale Vivo:",
            exc,
            flush=True,
        )

        cameras_vale_vivo = []

    monitoramento_visual_html = (
        gerar_monitoramento_visual_html(
            cameras_vale_vivo
        )
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

/* ==========================================================
   NAVEGACAO PRINCIPAL
   ========================================================== */

.nav-monitor {{
    max-width: 1500px;
    margin: 0 auto;
    padding: 18px 28px 0 28px;
}}

.nav-monitor-inner {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;

    padding: 7px;

    background: #10171c;
    border: 1px solid #29363e;
    border-radius: 12px;
}}

.nav-monitor a {{
    display: inline-flex;
    align-items: center;
    justify-content: center;

    min-height: 38px;
    padding: 0 16px;

    border-radius: 8px;

    color: #8fa0aa;
    text-decoration: none;

    font-size: 12px;
    font-weight: 700;
    letter-spacing: .35px;

    transition:
        background .18s ease,
        color .18s ease,
        border-color .18s ease;
}}

.nav-monitor a:hover {{
    color: #e8eef1;
    background: #182229;
}}

.nav-monitor a.ativo {{
    color: #f3f7f8;

    background: #1f2c33;

    box-shadow:
        inset 0 0 0 1px #3b515d;
}}

/* ==========================================================
   CONTEUDO DAS ABAS
   ========================================================== */

.painel-aba {{
    display: none;
}}

.painel-aba.ativa {{
    display: block;
}}

.vv-monitor {{
    display: grid;
    gap: 16px;
}}

.vv-intro {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 18px;

    padding: 16px 18px;

    border: 1px solid #25343d;
    border-radius: 11px;

    background: #11191e;
}}

.vv-titulo {{
    color: #e8eef1;

    font-size: 15px;
    font-weight: 800;
    letter-spacing: .35px;
}}

.vv-subtitulo {{
    margin-top: 5px;

    color: #82939d;

    font-size: 11px;
    line-height: 1.45;
}}

.vv-status {{
    display: inline-flex;
    align-items: center;
    gap: 6px;

    flex-shrink: 0;

    padding: 6px 10px;

    border-radius: 999px;

    font-size: 9px;
    font-weight: 800;
    letter-spacing: .35px;
}}

.vv-status.online {{
    color: #b7dbc4;
    background: #12241a;
    border: 1px solid #294b35;
}}

.vv-status.offline {{
    color: #d7a4a4;
    background: #2b1717;
    border: 1px solid #573030;
}}

.vv-navegacao {{
    display: grid;

    grid-template-columns:
        repeat(
            5,
            minmax(0,1fr)
        );

    gap: 8px;
}}

.vv-botao-camera {{
    min-height: 45px;

    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;

    padding: 9px 10px;

    color: #93a3ac;
    background: #11191e;

    border: 1px solid #26343c;
    border-radius: 8px;

    font-size: 10px;
    font-weight: 700;

    cursor: pointer;

    transition:
        border-color .15s ease,
        background .15s ease,
        color .15s ease;
}}

.vv-botao-camera:hover {{
    color: #dbe5e9;
    border-color: #40525d;
}}

.vv-botao-camera.ativo {{
    color: #d9ede0;

    background: #16231a;
    border-color: #3b6548;
}}

.vv-botao-camera.online
.vv-botao-status,
.vv-botao-camera.disponivel
.vv-botao-status {{
    color: #66c886;
}}

.vv-botao-camera.offline
.vv-botao-status {{
    color: #b96f6f;
}}

.vv-player-card {{
    overflow: hidden;

    border: 1px solid #25343d;
    border-radius: 12px;

    background: #10181d;
}}

.vv-player-topo {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;

    padding: 15px 17px;
}}

.vv-local {{
    color: #84a98e;

    font-size: 10px;
    font-weight: 800;
    letter-spacing: .55px;
    text-transform: uppercase;
}}

.vv-local-titulo {{
    margin-top: 3px;

    color: #edf2f4;

    font-size: 17px;
    font-weight: 800;
}}

.vv-local-descricao {{
    margin-top: 4px;

    color: #8999a2;

    font-size: 11px;
}}

.vv-fonte {{
    color: #6f8089;

    font-size: 10px;

    white-space: nowrap;
}}

.vv-video-wrap {{
    position: relative;

    width: 100%;
    aspect-ratio: 16 / 9;

    background: #05090b;
}}

.vv-video-wrap iframe {{
    position: absolute;
    inset: 0;

    width: 100%;
    height: 100%;

    border: 0;
}}

.vv-indisponivel {{
    position: absolute;
    inset: 0;

    align-items: center;
    justify-content: center;

    padding: 25px;

    text-align: center;

    background:
        radial-gradient(
            circle at center,
            #182229,
            #080d10 70%
        );
}}

.vv-indisponivel div {{
    display: grid;
    gap: 7px;
}}

.vv-indisponivel strong {{
    color: #d7a4a4;

    font-size: 14px;
}}

.vv-indisponivel span {{
    color: #7e8f98;

    font-size: 11px;
}}

.vv-rodape {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;

    padding: 11px 16px;

    color: #71818a;

    font-size: 10px;
    line-height: 1.4;
}}

.vv-rodape a {{
    flex-shrink: 0;

    padding: 6px 9px;

    border: 1px solid #33434c;
    border-radius: 6px;

    color: #a8bac3;

    text-decoration: none;

    font-size: 9px;
    font-weight: 800;
}}

.vv-rodape a:hover {{
    color: #e8eef1;
    border-color: #566b77;
}}

.vv-sem-dados {{
    padding: 40px;

    border: 1px solid #26343c;
    border-radius: 10px;

    color: #82929b;
    background: #0d1418;

    text-align: center;
}}

@media(max-width:900px) {{

    .vv-intro {{
        flex-direction: column;
    }}

    .vv-navegacao {{
        grid-template-columns:
            repeat(
                2,
                minmax(0,1fr)
            );
    }}

    .vv-player-topo {{
        flex-direction: column;
    }}

    .vv-rodape {{
        flex-direction: column;
        align-items: flex-start;
    }}

}}


.comparativo-lista {{
    display: grid;
    gap: 20px;
}}

.comparativo-card {{
    overflow: hidden;
}}

.comparativo-topo {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}}

.comparativo-intervalo {{
    padding: 5px 9px;

    border-radius: 999px;

    background: #10191e;
    border: 1px solid #30404a;

    color: #91a3ad;

    font-size: 9px;
    font-weight: 800;
    letter-spacing: .35px;
}}

.comparativo-dupla {{
    display: grid;

    grid-template-columns:
        repeat(
            2,
            minmax(0,1fr)
        );

    gap: 14px;

    margin-top: 16px;
}}

.comparativo-cena {{
    min-width: 0;

    padding: 12px;

    border-radius: 11px;

    background: #0d1418;

    border: 1px solid #26343c;
}}

.comparativo-rotulo {{
    display: inline-flex;

    margin-bottom: 10px;
    padding: 5px 8px;

    border-radius: 999px;

    font-size: 9px;
    font-weight: 800;
    letter-spacing: .35px;
}}

.comparativo-rotulo.anterior {{
    color: #aab7be;

    background: #172027;

    border: 1px solid #33434c;
}}

.comparativo-rotulo.atual {{
    color: #b6dac3;

    background: #12241a;

    border: 1px solid #294b35;
}}

.comparativo-imagem-wrap {{
    height: 360px;

    overflow: hidden;

    border-radius: 9px;

    background: #080d10;
}}

.comparativo-img {{
    display: block;

    width: 100%;
    height: 100%;

    object-fit: cover;
}}

.comparativo-img-vazia {{
    width: 100%;
    height: 100%;

    display: flex;
    align-items: center;
    justify-content: center;

    color: #70808a;
}}

.comparativo-meta {{
    display: grid;

    grid-template-columns:
        repeat(
            3,
            minmax(0,1fr)
        );

    gap: 7px;

    margin-top: 10px;
}}

.comparativo-meta div {{
    padding: 9px;

    border-radius: 7px;

    background: #111a1f;
}}

.comparativo-meta span {{
    font-size: 9px;
}}

.comparativo-meta strong {{
    font-size: 12px;
}}

.comparativo-aviso {{
    margin-top: 13px;

    color: #81919b;

    font-size: 11px;
    line-height: 1.5;
}}

.comparativo-sem-dados {{
    margin-top: 16px;

    padding: 30px;

    border-radius: 9px;

    background: #0d1418;

    color: #82929b;
}}

@media(max-width:900px) {{

    .comparativo-dupla {{
        grid-template-columns: 1fr;
    }}

    .comparativo-imagem-wrap {{
        height: 300px;
    }}

    .comparativo-meta {{
        grid-template-columns: 1fr;
    }}

}}


.sat-grid {{
    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(330px,1fr)
        );

    gap: 18px;
}}

.sat-card {{
    overflow: hidden;
}}

.sat-cabecalho {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
}}

.sat-badges {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
}}

.sat-badge {{
    display: inline-flex;

    padding:
        5px
        8px;

    border-radius: 999px;

    font-size: 9px;
    font-weight: 800;
    letter-spacing: .35px;

    border: 1px solid transparent;
}}

.sat-badge.bom {{
    color: #b7dbc4;
    background: #12241a;
    border-color: #294b35;
}}

.sat-badge.atencao {{
    color: #e3c98e;
    background: #292211;
    border-color: #57451f;
}}

.sat-badge.antigo {{
    color: #d7a4a4;
    background: #2b1717;
    border-color: #573030;
}}

.sat-badge.neutro {{
    color: #9cabb4;
    background: #131b20;
    border-color: #2b3941;
}}

.sat-imagem-wrap {{
    margin-top: 16px;

    width: 100%;
    height: 320px;

    overflow: hidden;

    border-radius: 10px;

    background: #0d1418;

    border: 1px solid #26343c;
}}

.sat-imagem {{
    width: 100%;
    height: 100%;

    object-fit: cover;

    display: block;
}}

.sat-imagem-vazia {{
    height: 320px;

    margin-top: 16px;

    display: flex;
    align-items: center;
    justify-content: center;

    background: #0d1418;

    border:
        1px solid
        #26343c;

    border-radius: 10px;

    color: #73838d;
}}

.sat-meta {{
    display: grid;

    grid-template-columns:
        repeat(
            2,
            1fr
        );

    gap: 8px;

    margin-top: 14px;
}}

.sat-meta div {{
    background: #0d1418;

    border-radius: 8px;

    padding: 11px;
}}

.sat-meta span {{
    font-size: 10px;
}}

.sat-meta strong {{
    font-size: 13px;
}}

.sat-aviso {{
    margin-top: 12px;

    color: #82929c;

    font-size: 11px;
    line-height: 1.4;
}}

.sat-sem-dados {{
    margin-top: 16px;

    padding: 30px;

    background: #0d1418;

    border-radius: 8px;

    color: #8a9aa4;
}}


.painel-placeholder {{
    min-height: 390px;

    display: flex;
    align-items: center;
    justify-content: center;
}}

.painel-placeholder-conteudo {{
    width: 100%;
    max-width: 850px;

    padding: 34px;

    background: #151d23;

    border: 1px solid #29363e;
    border-radius: 14px;

    text-align: center;
}}

.painel-placeholder-icone {{
    width: 52px;
    height: 52px;

    display: flex;
    align-items: center;
    justify-content: center;

    margin: 0 auto 18px auto;

    border-radius: 50%;

    background: #0d1418;
    border: 1px solid #30414b;

    color: #90a8b5;
    font-size: 24px;
}}

.painel-placeholder-titulo {{
    color: #eef3f5;

    font-size: 20px;
    font-weight: 700;
}}

.painel-placeholder-texto {{
    max-width: 650px;

    margin: 12px auto 0 auto;

    color: #8fa0aa;

    font-size: 14px;
    line-height: 1.6;
}}

.painel-placeholder-etapa {{
    display: inline-block;

    margin-top: 18px;
    padding: 7px 11px;

    border-radius: 999px;

    background: #0d1418;
    border: 1px solid #29363e;

    color: #8297a3;

    font-size: 11px;
    font-weight: 700;
    letter-spacing: .3px;
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

    .nav-monitor {{
        padding:
            14px
            14px
            0
            14px;
    }}

    .nav-monitor-inner {{
        display: grid;
        grid-template-columns:
            repeat(2,1fr);
    }}

    .nav-monitor a {{
        padding:
            0
            8px;

        font-size: 10px;
    }}

    main {{
        padding:
            20px
            14px;
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

<nav
    class="nav-monitor"
    id="nav-monitor-taquari"
    aria-label="Navegação principal do monitor"
>
    <div class="nav-monitor-inner">

        <a
            href="#visao-geral"
            data-aba="visao-geral"
            class="ativo"
        >
            VISÃO GERAL
        </a>

        <a
            href="#imagens-atuais"
            data-aba="imagens-atuais"
        >
            IMAGENS ATUAIS
        </a>

        <a
            href="#comparativo"
            data-aba="comparativo"
        >
            COMPARATIVO
        </a>

        <a
            href="#monitoramento-visual"
            data-aba="monitoramento-visual"
        >
            MONITORAMENTO VISUAL
        </a>

    </div>
</nav>

<main>

<section
    id="visao-geral"
    class="painel-aba ativa"
>

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

</section>


<!-- ======================================================
     IMAGENS ATUAIS
     ====================================================== -->

<section
    id="imagens-atuais"
    class="painel-aba"
>

    <div class="secao">

        <div
            class="titulo"
            style="
                margin-bottom:14px;
                font-size:14px;
            "
        >
            IMAGENS ATUAIS — ÚLTIMA CENA ÚTIL
        </div>

        {imagens_satelite_html}

    </div>

</section>


<!-- ======================================================
     COMPARATIVO
     ====================================================== -->

<section
    id="comparativo"
    class="painel-aba"
>

    <div class="secao">

        <div
            class="titulo"
            style="
                margin-bottom:14px;
                font-size:14px;
            "
        >
            COMPARATIVO DE IMAGENS
        </div>

        {comparativo_satelite_html}

    </div>

</section>


<!-- ======================================================
     MONITORAMENTO VISUAL
     ====================================================== -->

<section
    id="monitoramento-visual"
    class="painel-aba"
>

    <div class="secao">

        {monitoramento_visual_html}

    </div>

</section>

</main>


<script>
(function() {{

    function normalizarAba() {{

        var hash = (
            window.location.hash
            || "#visao-geral"
        );

        var aba = hash.replace(
            "#",
            ""
        );

        var permitidas = [
            "visao-geral",
            "imagens-atuais",
            "comparativo",
            "monitoramento-visual"
        ];

        if (
            permitidas.indexOf(aba)
            === -1
        ) {{
            aba = "visao-geral";
        }}

        return aba;
    }}


    function ativarAba() {{

        var aba = normalizarAba();

        var paineis = document.querySelectorAll(
            ".painel-aba"
        );

        var links = document.querySelectorAll(
            "#nav-monitor-taquari [data-aba]"
        );

        paineis.forEach(
            function(painel) {{

                painel.classList.remove(
                    "ativa"
                );

            }}
        );

        links.forEach(
            function(link) {{

                link.classList.remove(
                    "ativo"
                );

            }}
        );

        var painelAtivo = document.getElementById(
            aba
        );

        var linkAtivo = document.querySelector(
            '#nav-monitor-taquari [data-aba="'
            + aba
            + '"]'
        );

        if (painelAtivo) {{
            painelAtivo.classList.add(
                "ativa"
            );
        }}

        if (linkAtivo) {{
            linkAtivo.classList.add(
                "ativo"
            );
        }}

        window.scrollTo(
            0,
            0
        );
    }}


    window.addEventListener(
        "hashchange",
        ativarAba
    );


    if (
        document.readyState
        === "loading"
    ) {{

        document.addEventListener(
            "DOMContentLoaded",
            ativarAba
        );

    }}
    else {{

        ativarAba();

    }}

}})();
</script>

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

    marcar_etapa(
        "inicio"
    )

    log(
        "=" * 55
    )

    log(
        "Nova coleta V3"
    )

    marcar_etapa(
        "coleta_estacoes_ana"
    )

    recebidos = []

    por_estacao = {}

    for nome, cfg in (
        ESTACOES.items()
    ):

        try:

            marcar_etapa(
                "ana_estacao_"
                + str(nome)
            )

            dados = buscar_ana(
                nome,
                cfg["codigo"]
            )

            marcar_etapa(
                "ana_estacao_ok_"
                + str(nome)
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

    marcar_etapa(
        "barragens_atual"
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

    # ========================================================
    # HISTORICO DAS BARRAGENS
    #
    # O proprio modulo limita a atualizacao para 30 minutos.
    # Falha aqui nao interrompe o monitor principal.
    # ========================================================

    marcar_etapa(
        "barragens_historico"
    )

    try:

        resultado_hist_barragens = (
            atualizar_historico_barragens()
        )

        if (
            resultado_hist_barragens.get(
                "executou"
            )
        ):

            if resultado_hist_barragens.get(
                "ok"
            ):

                log(
                    (
                        "Historico barragens atualizado: "
                        f'{resultado_hist_barragens.get("horario_total", 0)} '
                        "horarios / "
                        f'{resultado_hist_barragens.get("diario_total", 0)} '
                        "diarios"
                    )
                )

            else:

                log(
                    (
                        "ERRO HISTORICO BARRAGENS: "
                        + str(
                            resultado_hist_barragens.get(
                                "erro",
                                "-"
                            )
                        )
                    )
                )

    except Exception as e:

        log(
            (
                "ERRO HISTORICO BARRAGENS: "
                + str(e)
            )
        )

    marcar_etapa(
        "meteorologia"
    )

    meteo = coletar_meteorologia()

    marcar_etapa(
        "gerando_dashboard"
    )

    gerar_dashboard(
        por_estacao,
        modelo,
        meteo,
        barragens
    )

    # ========================================================
    # WHATSAPP AUTOMATICO
    # ========================================================

    marcar_etapa(
        "salvando_status"
    )

    salvar_status(
        por_estacao,
        modelo
    )

    log(
        "Dashboard V3 atualizado."
    )

    marcar_etapa(
        "ciclo_monitor_cloud_concluido"
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
