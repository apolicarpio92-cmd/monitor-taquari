from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE = Path(__file__).resolve().parent

DIR_DADOS = BASE / "dados"
DIR_HIST = BASE / "historico"

DIR_DADOS.mkdir(
    parents=True,
    exist_ok=True
)

DIR_HIST.mkdir(
    parents=True,
    exist_ok=True
)


URL = (
    "https://nivelguaiba.com.br/"
    "reservatorios/taquari-antas"
)

ARQ_HIST = (
    DIR_HIST
    / "barragens_historico.csv"
)

ARQ_DEBUG = (
    DIR_DADOS
    / "barragens_debug.txt"
)

TIMEOUT = 30


BARRAGENS = [
    "Castro Alves",
    "Monte Claro",
    "14 de Julho",
]


# ============================================================
# NUMERO
# ============================================================

def numero(valor):

    if valor is None:
        return None

    valor = (
        str(valor)
        .strip()
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return float(valor)
    except Exception:
        return None


# ============================================================
# TEXTO DA PAGINA
# ============================================================

def baixar():

    r = requests.get(
        URL,
        timeout=TIMEOUT,
        headers={
            "User-Agent":
                "Mozilla/5.0 "
                "Monitor-Taquari-V3.1"
        },
    )

    r.raise_for_status()

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    texto = soup.get_text(
        "\n",
        strip=True
    )

    ARQ_DEBUG.write_text(
        texto,
        encoding="utf-8"
    )

    return soup, texto


# ============================================================
# LOCALIZA BLOCO DA BARRAGEM
# ============================================================

def bloco_por_html(
    soup,
    nome,
):

    candidatos = soup.find_all(
        [
            "h2",
            "h3",
            "h4",
            "strong",
        ]
    )

    alvo = None

    for tag in candidatos:

        txt = " ".join(
            tag.stripped_strings
        )

        if (
            txt.strip().lower()
            == nome.lower()
        ):

            alvo = tag
            break

    if alvo is None:
        return None

    partes = []

    atual = alvo

    limite = 0

    while atual is not None:

        atual = atual.find_next()

        if atual is None:
            break

        if (
            atual.name
            in [
                "h2",
                "h3",
            ]
        ):

            titulo = " ".join(
                atual.stripped_strings
            )

            if (
                titulo.strip()
                and titulo.strip().lower()
                != nome.lower()
            ):

                break

        txt = " ".join(
            atual.stripped_strings
        )

        if txt:
            partes.append(
                txt
            )

        limite += 1

        if limite > 150:
            break

    if not partes:
        return None

    return "\n".join(
        partes
    )


# ============================================================
# FALLBACK POR TEXTO
# ============================================================

def bloco_por_texto(
    texto,
    nome,
):

    pos = texto.lower().find(
        nome.lower()
    )

    if pos < 0:
        return ""

    proximos = []

    for outro in BARRAGENS:

        if outro == nome:
            continue

        p = texto.lower().find(
            outro.lower(),
            pos + len(nome)
        )

        if p > pos:
            proximos.append(
                p
            )

    fim = (
        min(proximos)
        if proximos
        else min(
            len(texto),
            pos + 6000
        )
    )

    return texto[
        pos:fim
    ]


# ============================================================
# EXTRAI DADOS
# ============================================================

def extrair(
    nome,
    bloco,
):

    bloco_normal = re.sub(
        r"\s+",
        " ",
        bloco
    )

    # --------------------------------------------------------
    # AFLUENCIA
    # --------------------------------------------------------

    entra = None

    m = re.search(
        r"\bentra\s+"
        r"([\d\.,]+)"
        r"\s*m[³3]/s",
        bloco_normal,
        re.I,
    )

    if m:

        entra = numero(
            m.group(1)
        )

    # --------------------------------------------------------
    # DEFLUENCIA / SAIDA
    # --------------------------------------------------------

    sai = None

    padroes_saida = [
        r"\bsai\s+([\d\.,]+)\s*m[³3]/s",
        r"\bsaindo\s+([\d\.,]+)\s*m[³3]/s",
        r"([\d\.,]+)\s*m[³3]/s\s+descem daqui",
    ]

    for padrao in padroes_saida:

        m = re.search(
            padrao,
            bloco_normal,
            re.I,
        )

        if m:

            sai = numero(
                m.group(1)
            )

            if sai is not None:
                break

    # --------------------------------------------------------
    # NIVEL
    # --------------------------------------------------------

    nivel = None

    m = re.search(
        r"\bN[ií]vel\s+"
        r"([\d\.,]+)"
        r"\s*m\b",
        bloco_normal,
        re.I,
    )

    if m:

        nivel = numero(
            m.group(1)
        )

    # --------------------------------------------------------
    # HORARIO DA FONTE
    # --------------------------------------------------------

    hora = None

    padroes_hora = [
        r"\bhoje\s+([0-2]?\d:[0-5]\d)",
        r"\bleitura\s+de\s+([0-2]?\d:[0-5]\d)",
    ]

    for p in padroes_hora:

        m = re.search(
            p,
            bloco_normal,
            re.I,
        )

        if m:

            hora = m.group(1)
            break

    agora = datetime.now()

    if hora:

        try:

            h, mi = [
                int(x)
                for x
                in hora.split(":")
            ]

            data_hora = agora.replace(
                hour=h,
                minute=mi,
                second=0,
                microsecond=0,
            )

        except Exception:

            data_hora = agora

    else:

        data_hora = agora

    return {
        "nome":
            nome,

        "data_hora":
            data_hora,

        "entra":
            entra,

        "sai":
            sai,

        "nivel":
            nivel,

        "fonte":
            "CERAN / Nivel Guaiba",
    }


# ============================================================
# HISTORICO
# ============================================================

def carregar_historico():

    dados = []

    if not ARQ_HIST.exists():
        return dados

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

                dados.append(
                    {
                        "nome":
                            row["nome"],

                        "data_hora":
                            datetime.strptime(
                                row["data_hora"],
                                "%Y-%m-%d %H:%M:%S"
                            ),

                        "entra":
                            (
                                float(
                                    row["entra"]
                                    .replace(",", ".")
                                )
                                if row.get(
                                    "entra"
                                )
                                else None
                            ),

                        "sai":
                            (
                                float(
                                    row["sai"]
                                    .replace(",", ".")
                                )
                                if row.get(
                                    "sai"
                                )
                                else None
                            ),

                        "nivel":
                            (
                                float(
                                    row["nivel"]
                                    .replace(",", ".")
                                )
                                if row.get(
                                    "nivel"
                                )
                                else None
                            ),
                    }
                )

            except Exception:
                pass

    return dados


def salvar_historico(
    novos,
):

    antigos = carregar_historico()

    mapa = {}

    for r in (
        antigos
        + novos
    ):

        chave = (
            r["nome"],
            r["data_hora"].strftime(
                "%Y-%m-%d %H:%M"
            ),
        )

        mapa[
            chave
        ] = r

    dados = sorted(
        mapa.values(),
        key=lambda x:
            (
                x["nome"],
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
                "nome",
                "data_hora",
                "entra",
                "sai",
                "nivel",
            ]
        )

        for r in dados:

            writer.writerow(
                [
                    r["nome"],

                    r["data_hora"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),

                    (
                        str(
                            r["entra"]
                        ).replace(
                            ".",
                            ","
                        )
                        if r["entra"]
                        is not None
                        else ""
                    ),

                    (
                        str(
                            r["sai"]
                        ).replace(
                            ".",
                            ","
                        )
                        if r["sai"]
                        is not None
                        else ""
                    ),

                    (
                        str(
                            r["nivel"]
                        ).replace(
                            ".",
                            ","
                        )
                        if r["nivel"]
                        is not None
                        else ""
                    ),
                ]
            )

    return dados


# ============================================================
# TENDENCIA
# ============================================================

def tendencia(
    atual,
    anterior,
):

    if (
        atual is None
        or anterior is None
        or anterior == 0
    ):

        return {
            "seta": "=",
            "percentual": None,
            "diferenca": None,
        }

    diferenca = (
        atual
        - anterior
    )

    percentual = (
        diferenca
        / anterior
        * 100
    )

    if percentual > 1.0:

        seta = "↑"

    elif percentual < -1.0:

        seta = "↓"

    else:

        seta = "="

    return {
        "seta":
            seta,

        "percentual":
            percentual,

        "diferenca":
            diferenca,
    }


# ============================================================
# COLETOR PRINCIPAL
# ============================================================

def coletar_barragens():

    soup, texto = baixar()

    atuais = []

    for nome in BARRAGENS:

        bloco = bloco_por_html(
            soup,
            nome
        )

        if not bloco:

            bloco = bloco_por_texto(
                texto,
                nome
            )

        dado = extrair(
            nome,
            bloco or ""
        )

        atuais.append(
            dado
        )

    historico_anterior = (
        carregar_historico()
    )

    resultado = []

    for atual in atuais:

        anteriores = [
            r
            for r in historico_anterior
            if (
                r["nome"]
                == atual["nome"]
                and r["sai"]
                is not None
                and r["data_hora"]
                < atual["data_hora"]
            )
        ]

        anterior = (
            anteriores[-1]
            if anteriores
            else None
        )

        t = tendencia(
            atual["sai"],
            (
                anterior["sai"]
                if anterior
                else None
            )
        )

        atual[
            "seta"
        ] = t["seta"]

        atual[
            "variacao_pct"
        ] = t[
            "percentual"
        ]

        atual[
            "variacao_m3s"
        ] = t[
            "diferenca"
        ]

        resultado.append(
            atual
        )

    salvar_historico(
        atuais
    )

    return resultado


# ============================================================
# TESTE DIRETO
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print(" BARRAGENS TAQUARI-ANTAS")
    print("=" * 70)

    dados = coletar_barragens()

    for d in dados:

        print()
        print(d["nome"])

        print(
            "Horario:",
            d["data_hora"].strftime(
                "%d/%m/%Y %H:%M"
            )
        )

        print(
            "Entra:",
            d["entra"]
        )

        print(
            "Sai:",
            d["sai"],
            d["seta"]
        )

        print(
            "Nivel:",
            d["nivel"]
        )

        print(
            "Variacao %:",
            d["variacao_pct"]
        )
