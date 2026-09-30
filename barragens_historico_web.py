from __future__ import annotations

import csv
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE = Path(__file__).resolve().parent

DIR_HIST = BASE / "historico"

DIR_HIST.mkdir(
    parents=True,
    exist_ok=True,
)

ARQ_HORARIO = (
    DIR_HIST
    / "barragens_historico.csv"
)

ARQ_DIARIO = (
    DIR_HIST
    / "barragens_diario.csv"
)

URL = (
    "https://nivelguaiba.com.br/"
    "reservatorios/taquari-antas"
)

BARRAGENS = {
    "Castro Alves":
        "elo-castro-alves",

    "Monte Claro":
        "elo-monte-claro",

    "14 de Julho":
        "elo-14-de-julho",
}

# O monitor roda a cada 5 minutos.
# A serie historica nao precisa ser baixada nesse ritmo.
INTERVALO_ATUALIZACAO = 30 * 60

_ULTIMA_ATUALIZACAO = 0.0


# ============================================================
# NUMEROS
# ============================================================

def numero_br(valor):

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    texto = (
        texto
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return float(texto)

    except Exception:
        return None


def numero_csv(valor):

    if valor is None:
        return ""

    return (
        str(
            round(
                float(valor),
                2,
            )
        )
        .replace(".", ",")
    )


# ============================================================
# DOWNLOAD
# ============================================================

def baixar():

    sessao = requests.Session()

    sessao.headers.update(
        {
            "User-Agent":
                (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/153 Safari/537.36"
                ),

            "Accept-Language":
                "pt-BR,pt;q=0.9,en;q=0.8",

            "Cache-Control":
                "no-cache",
        }
    )

    resposta = sessao.get(
        URL,
        timeout=30,
    )

    resposta.raise_for_status()

    return resposta.text


# ============================================================
# DATA DA PAGINA
# ============================================================

def descobrir_data_pagina(soup):

    for script in soup.find_all(
        "script",
        attrs={
            "type":
                "application/ld+json"
        },
    ):

        texto = (
            script.string
            or script.get_text(
                " ",
                strip=True,
            )
            or ""
        )

        m = re.search(
            r'"dateModified"\s*:\s*"'
            r'(\d{4}-\d{2}-\d{2})',
            texto,
        )

        if m:

            return datetime.strptime(
                m.group(1),
                "%Y-%m-%d",
            ).date()

    return datetime.now().date()


# ============================================================
# EXPRESSOES
# ============================================================

RE_HORA = re.compile(
    r"^\s*"
    r"(\d{1,2}:\d{2})"
    r"\s*·\s*"
    r"entra\s+([\d\.,]+)"
    r"\s*·\s*"
    r"sai\s+([\d\.,]+)"
    r"\s*m[³3]/s"
    r"\s*$",
    re.I,
)

RE_DIA = re.compile(
    r"^\s*"
    r"(\d{1,2}/\d{1,2})"
    r"\s*·\s*"
    r"entra\s+([\d\.,]+)"
    r"\s*·\s*"
    r"sai\s+([\d\.,]+)"
    r"\s*m[³3]/s"
    r"\s*$",
    re.I,
)


# ============================================================
# EXTRACAO
# ============================================================

def extrair_series():

    html = baixar()

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    data_pagina = descobrir_data_pagina(
        soup
    )

    horario = []
    diario = []

    for nome, article_id in BARRAGENS.items():

        artigo = soup.find(
            "article",
            id=article_id,
        )

        if artigo is None:

            print(
                "[BARRAGENS-HIST] Artigo nao encontrado:",
                nome,
                flush=True,
            )

            continue

        for elemento in artigo.find_all(
            attrs={
                "data-v":
                    True
            },
        ):

            valor = str(
                elemento.get(
                    "data-v",
                    ""
                )
            ).strip()

            # ------------------------------------------------
            # HORARIO
            # ------------------------------------------------

            m = RE_HORA.match(
                valor
            )

            if m:

                dt = datetime.strptime(
                    (
                        data_pagina.strftime(
                            "%Y-%m-%d"
                        )
                        + " "
                        + m.group(1)
                    ),
                    "%Y-%m-%d %H:%M",
                )

                horario.append(
                    {
                        "nome":
                            nome,

                        "data_hora":
                            dt,

                        "entra":
                            numero_br(
                                m.group(2)
                            ),

                        "sai":
                            numero_br(
                                m.group(3)
                            ),

                        "nivel":
                            None,

                        "origem":
                            "CERAN/NivelGuaiba-html",
                    }
                )

                continue

            # ------------------------------------------------
            # DIARIO
            # ------------------------------------------------

            m = RE_DIA.match(
                valor
            )

            if m:

                dia, mes = [
                    int(x)
                    for x
                    in m.group(1).split("/")
                ]

                ano = data_pagina.year

                if (
                    mes > data_pagina.month
                    and data_pagina.month <= 2
                ):

                    ano -= 1

                data = datetime(
                    ano,
                    mes,
                    dia,
                ).date()

                diario.append(
                    {
                        "nome":
                            nome,

                        "data":
                            data,

                        "entra":
                            numero_br(
                                m.group(2)
                            ),

                        "sai":
                            numero_br(
                                m.group(3)
                            ),

                        "origem":
                            "CERAN/NivelGuaiba-html",
                    }
                )

    # --------------------------------------------------------
    # REMOVE DUPLICACOES DO PROPRIO HTML
    # --------------------------------------------------------

    mapa_hora = {}

    for r in horario:

        mapa_hora[
            (
                r["nome"],
                r["data_hora"],
            )
        ] = r

    horario = sorted(
        mapa_hora.values(),
        key=lambda x: (
            x["nome"],
            x["data_hora"],
        ),
    )

    mapa_dia = {}

    for r in diario:

        mapa_dia[
            (
                r["nome"],
                r["data"],
            )
        ] = r

    diario = sorted(
        mapa_dia.values(),
        key=lambda x: (
            x["nome"],
            x["data"],
        ),
    )

    return horario, diario


# ============================================================
# HORARIO EXISTENTE
# ============================================================

def carregar_horario_existente():

    resultado = []

    if not ARQ_HORARIO.exists():
        return resultado

    with ARQ_HORARIO.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(
            f,
            delimiter=";",
        )

        for row in reader:

            try:

                dt = datetime.strptime(
                    row["data_hora"],
                    "%Y-%m-%d %H:%M:%S",
                )

            except Exception:

                try:

                    dt = datetime.strptime(
                        row["data_hora"],
                        "%Y-%m-%d %H:%M",
                    )

                except Exception:

                    continue

            resultado.append(
                {
                    "nome":
                        row.get(
                            "nome",
                            ""
                        ),

                    "data_hora":
                        dt,

                    "entra":
                        numero_br(
                            row.get(
                                "entra"
                            )
                        ),

                    "sai":
                        numero_br(
                            row.get(
                                "sai"
                            )
                        ),

                    "nivel":
                        numero_br(
                            row.get(
                                "nivel"
                            )
                        ),

                    "origem":
                        (
                            row.get(
                                "origem"
                            )
                            or "coleta-monitor"
                        ),
                }
            )

    return resultado


def salvar_horario(novos):

    antigos = carregar_horario_existente()

    mapa = {}

    # Web primeiro.
    for r in novos:

        mapa[
            (
                r["nome"],
                r["data_hora"],
            )
        ] = dict(r)

    # Histórico do monitor depois.
    # Assim preserva nível quando já existir.
    for r in antigos:

        chave = (
            r["nome"],
            r["data_hora"],
        )

        atual = mapa.get(
            chave
        )

        if atual:

            combinado = dict(
                atual
            )

            for campo in (
                "entra",
                "sai",
                "nivel",
            ):

                if r.get(
                    campo
                ) is not None:

                    combinado[
                        campo
                    ] = r[
                        campo
                    ]

            combinado[
                "origem"
            ] = r.get(
                "origem",
                "coleta-monitor",
            )

            mapa[
                chave
            ] = combinado

        else:

            mapa[
                chave
            ] = dict(r)

    dados = sorted(
        mapa.values(),
        key=lambda x: (
            x["nome"],
            x["data_hora"],
        ),
    )

    with ARQ_HORARIO.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.writer(
            f,
            delimiter=";",
        )

        writer.writerow(
            [
                "nome",
                "data_hora",
                "entra",
                "sai",
                "nivel",
                "origem",
            ]
        )

        for r in dados:

            writer.writerow(
                [
                    r["nome"],

                    r["data_hora"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),

                    numero_csv(
                        r.get(
                            "entra"
                        )
                    ),

                    numero_csv(
                        r.get(
                            "sai"
                        )
                    ),

                    numero_csv(
                        r.get(
                            "nivel"
                        )
                    ),

                    r.get(
                        "origem",
                        "",
                    ),
                ]
            )

    return dados


# ============================================================
# DIARIO EXISTENTE
# ============================================================

def carregar_diario_existente():

    resultado = []

    if not ARQ_DIARIO.exists():
        return resultado

    with ARQ_DIARIO.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(
            f,
            delimiter=";",
        )

        for row in reader:

            try:

                data = datetime.strptime(
                    row["data"],
                    "%Y-%m-%d",
                ).date()

            except Exception:

                continue

            resultado.append(
                {
                    "nome":
                        row.get(
                            "nome",
                            ""
                        ),

                    "data":
                        data,

                    "entra":
                        numero_br(
                            row.get(
                                "entra"
                            )
                        ),

                    "sai":
                        numero_br(
                            row.get(
                                "sai"
                            )
                        ),

                    "origem":
                        (
                            row.get(
                                "origem"
                            )
                            or ""
                        ),
                }
            )

    return resultado


def salvar_diario(novos):

    mapa = {}

    for r in (
        carregar_diario_existente()
        + novos
    ):

        mapa[
            (
                r["nome"],
                r["data"],
            )
        ] = dict(r)

    dados = sorted(
        mapa.values(),
        key=lambda x: (
            x["nome"],
            x["data"],
        ),
    )

    with ARQ_DIARIO.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.writer(
            f,
            delimiter=";",
        )

        writer.writerow(
            [
                "nome",
                "data",
                "entra",
                "sai",
                "origem",
            ]
        )

        for r in dados:

            writer.writerow(
                [
                    r["nome"],

                    r["data"].strftime(
                        "%Y-%m-%d"
                    ),

                    numero_csv(
                        r.get(
                            "entra"
                        )
                    ),

                    numero_csv(
                        r.get(
                            "sai"
                        )
                    ),

                    r.get(
                        "origem",
                        "",
                    ),
                ]
            )

    return dados


# ============================================================
# ATUALIZACAO PUBLICA
# ============================================================

def atualizar_historico_barragens(
    forcar=False,
):

    global _ULTIMA_ATUALIZACAO

    agora_ts = time.time()

    if (
        not forcar
        and _ULTIMA_ATUALIZACAO > 0
        and (
            agora_ts
            - _ULTIMA_ATUALIZACAO
        ) < INTERVALO_ATUALIZACAO
    ):

        return {
            "ok":
                True,

            "executou":
                False,

            "motivo":
                "intervalo",
        }

    try:

        horario, diario = extrair_series()

        horario_final = salvar_horario(
            horario
        )

        diario_final = salvar_diario(
            diario
        )

        _ULTIMA_ATUALIZACAO = agora_ts

        resultado = {
            "ok":
                True,

            "executou":
                True,

            "horarios_extraidos":
                len(horario),

            "diarios_extraidos":
                len(diario),

            "horario_total":
                len(horario_final),

            "diario_total":
                len(diario_final),

            "atualizado_em":
                datetime.now().isoformat(
                    timespec="seconds"
                ),
        }

        print(
            (
                "[BARRAGENS-HIST] "
                f"horarios={len(horario)} "
                f"diarios={len(diario)} "
                f"total_h={len(horario_final)} "
                f"total_d={len(diario_final)}"
            ),
            flush=True,
        )

        return resultado

    except Exception as e:

        print(
            (
                "[BARRAGENS-HIST] ERRO: "
                + str(e)
            ),
            flush=True,
        )

        return {
            "ok":
                False,

            "executou":
                True,

            "erro":
                str(e),
        }


# ============================================================
# EXECUCAO MANUAL
# ============================================================

if __name__ == "__main__":

    resultado = (
        atualizar_historico_barragens(
            forcar=True
        )
    )

    print("")
    print(resultado)
