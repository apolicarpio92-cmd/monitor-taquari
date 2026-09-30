from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

ARQ_HIST = (
    BASE_DIR
    / "historico"
    / "telemetria_historico.csv"
)


# ============================================================
# CONVERSOES
# ============================================================

def para_float(valor):

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    texto = texto.replace(
        ".",
        ""
    ).replace(
        ",",
        "."
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
                formato
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
# CARREGA HISTORICO
# ============================================================

def carregar_historico():

    if not ARQ_HIST.exists():

        return {
            "ok": False,
            "erro": (
                "Histórico de telemetria "
                "ainda não disponível."
            ),
            "series": {},
        }

    registros = []

    try:

        with ARQ_HIST.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as arquivo:

            leitor = csv.DictReader(
                arquivo,
                delimiter=";",
            )

            for linha in leitor:

                data_hora = para_data(
                    linha.get(
                        "data_hora"
                    )
                )

                nivel = para_float(
                    linha.get(
                        "nivel_m"
                    )
                )

                vazao = para_float(
                    linha.get(
                        "vazao"
                    )
                )

                chuva = para_float(
                    linha.get(
                        "chuva"
                    )
                )

                estacao = (
                    linha.get(
                        "estacao",
                        ""
                    )
                    or ""
                ).strip()

                codigo = (
                    linha.get(
                        "codigo",
                        ""
                    )
                    or ""
                ).strip()

                if data_hora is None:
                    continue

                registros.append(
                    {
                        "estacao": estacao,
                        "codigo": codigo,
                        "data_hora": data_hora,
                        "nivel": nivel,
                        "vazao": vazao,
                        "chuva": chuva,
                    }
                )

    except Exception as e:

        return {
            "ok": False,
            "erro": str(e),
            "series": {},
        }

    if not registros:

        return {
            "ok": False,
            "erro": (
                "Histórico de telemetria vazio."
            ),
            "series": {},
        }

    registros.sort(
        key=lambda r: r[
            "data_hora"
        ]
    )

    return {
        "ok": True,
        "registros": registros,
    }


# ============================================================
# PREPARA SERIES
# ============================================================

def preparar_series():

    dados = carregar_historico()

    if not dados.get(
        "ok"
    ):

        return dados

    registros = dados[
        "registros"
    ]

    ultima_data = max(
        r["data_hora"]
        for r in registros
    )

    series = {
        "santa_nivel": [],
        "linha_nivel": [],
        "linha_vazao": [],
    }

    for r in registros:

        estacao_normalizada = (
            r["estacao"]
            .lower()
            .replace("é", "e")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("í", "i")
            .replace("á", "a")
            .replace("ã", "a")
            .replace("ç", "c")
        )

        item_base = {
            "t": (
                r["data_hora"]
                .isoformat(
                    timespec="minutes"
                )
            ),
            "rotulo": (
                r["data_hora"]
                .strftime(
                    "%d/%m %H:%M"
                )
            ),
        }

        if (
            "santa tereza"
            in estacao_normalizada
            or r["codigo"] == "86472600"
        ):

            if r["nivel"] is not None:

                series[
                    "santa_nivel"
                ].append(
                    {
                        **item_base,
                        "v": r["nivel"],
                    }
                )

        if (
            "linha jose julio"
            in estacao_normalizada
            or r["codigo"] == "86472000"
        ):

            if r["nivel"] is not None:

                series[
                    "linha_nivel"
                ].append(
                    {
                        **item_base,
                        "v": r["nivel"],
                    }
                )

            if r["vazao"] is not None:

                series[
                    "linha_vazao"
                ].append(
                    {
                        **item_base,
                        "v": r["vazao"],
                    }
                )

    return {
        "ok": True,
        "ultima_data": (
            ultima_data.isoformat(
                timespec="minutes"
            )
        ),
        "series": series,
    }


# ============================================================
# HTML
# ============================================================

def gerar_html_graficos_historicos():

    dados = preparar_series()

    if not dados.get(
        "ok"
    ):

        erro = (
            dados.get(
                "erro",
                "Histórico indisponível."
            )
        )

        return f"""
<section class="hist-painel">

    <div class="hist-titulo">
        EVOLUÇÃO HIDROLÓGICA
    </div>

    <div class="hist-sem-dados">
        {erro}
    </div>

</section>
"""

    payload = json.dumps(
        dados,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )

    return """
<style>

.hist-painel {
    margin-top:18px;
    margin-bottom:18px;
    padding:20px;
    border-radius:16px;
    background:#151e23;
    border:1px solid #2b3941;
    color:#f4f7f8;
}

.hist-topo {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:16px;
    flex-wrap:wrap;
    margin-bottom:18px;
}

.hist-titulo {
    color:#8fb8d0;
    font-size:15px;
    font-weight:800;
    letter-spacing:.04em;
}

.hist-subtitulo {
    margin-top:4px;
    color:#819ba9;
    font-size:11px;
}

.hist-botoes {
    display:flex;
    gap:7px;
    flex-wrap:wrap;
}

.hist-btn {
    border:1px solid #344852;
    background:#0c1418;
    color:#9fb8c5;
    border-radius:8px;
    padding:7px 12px;
    font-size:11px;
    font-weight:700;
    cursor:pointer;
}

.hist-btn:hover {
    border-color:#66889a;
}

.hist-btn.ativo {
    background:#243640;
    border-color:#79a7be;
    color:#fff;
}

.hist-grid {
    display:grid;
    grid-template-columns:
        repeat(2,minmax(0,1fr));
    gap:14px;
}

.hist-card {
    background:#10191e;
    border:1px solid #293941;
    border-radius:14px;
    padding:15px;
    min-width:0;
}

.hist-card-largo {
    grid-column:1 / -1;
}

.hist-card-titulo {
    color:#9bb9c8;
    font-size:12px;
    font-weight:800;
    margin-bottom:4px;
}

.hist-card-unidade {
    color:#668495;
    font-size:10px;
}

.hist-metricas {
    display:grid;
    grid-template-columns:
        repeat(4,minmax(0,1fr));
    gap:7px;
    margin-top:12px;
    margin-bottom:12px;
}

.hist-metrica {
    background:#0b1317;
    border-radius:9px;
    padding:8px 9px;
}

.hist-metrica span {
    display:block;
    color:#6f8c9c;
    font-size:9px;
    margin-bottom:3px;
}

.hist-metrica strong {
    display:block;
    color:#fff;
    font-size:13px;
}

.hist-svg-wrap {
    width:100%;
    overflow:hidden;
}

.hist-svg {
    width:100%;
    height:245px;
    display:block;
}

.hist-gridline {
    stroke:#27363e;
    stroke-width:1;
}

.hist-eixo-label {
    fill:#698391;
    font-size:10px;
}

.hist-linha {
    fill:none;
    stroke:#8bc0dd;
    stroke-width:2.5;
    stroke-linejoin:round;
    stroke-linecap:round;
}

.hist-area {
    fill:rgba(139,192,221,.08);
}

.hist-ponto-final {
    fill:#d8eef8;
}

.hist-tooltip {
    position:fixed;
    display:none;
    z-index:999999;
    pointer-events:none;
    background:#080f13;
    border:1px solid #3a505b;
    color:#fff;
    padding:7px 9px;
    border-radius:7px;
    font-size:11px;
    box-shadow:
        0 5px 20px rgba(0,0,0,.35);
}

.hist-sem-dados {
    margin-top:10px;
    color:#9aadb6;
    font-size:12px;
}

.hist-rodape {
    margin-top:12px;
    color:#66818e;
    font-size:10px;
}

@media (max-width:900px) {

    .hist-grid {
        grid-template-columns:1fr;
    }

    .hist-card-largo {
        grid-column:auto;
    }

    .hist-metricas {
        grid-template-columns:
            repeat(2,minmax(0,1fr));
    }
}

@media (max-width:560px) {

    .hist-painel {
        padding:14px;
    }

    .hist-svg {
        height:210px;
    }

    .hist-botoes {
        width:100%;
    }

    .hist-btn {
        flex:1;
    }
}

</style>

<section
    id="historico-hidrologico"
    class="hist-painel"
>

    <div class="hist-topo">

        <div>

            <div class="hist-titulo">
                EVOLUÇÃO HIDROLÓGICA
            </div>

            <div class="hist-subtitulo">
                Histórico observado das estações
            </div>

        </div>

        <div class="hist-botoes">

            <button
                type="button"
                class="hist-btn ativo"
                data-horas="24"
            >
                24 HORAS
            </button>

            <button
                type="button"
                class="hist-btn"
                data-horas="48"
            >
                48 HORAS
            </button>

            <button
                type="button"
                class="hist-btn"
                data-horas="168"
            >
                7 DIAS
            </button>

        </div>

    </div>

    <div class="hist-grid">

        <div class="hist-card">

            <div class="hist-card-titulo">
                SANTA TEREZA — NÍVEL
            </div>

            <div class="hist-card-unidade">
                metros
            </div>

            <div
                class="hist-metricas"
                id="hist-metricas-santa"
            ></div>

            <div
                class="hist-svg-wrap"
                id="grafico-santa"
            ></div>

        </div>

        <div class="hist-card">

            <div class="hist-card-titulo">
                LINHA JOSÉ JÚLIO — NÍVEL
            </div>

            <div class="hist-card-unidade">
                metros
            </div>

            <div
                class="hist-metricas"
                id="hist-metricas-linha"
            ></div>

            <div
                class="hist-svg-wrap"
                id="grafico-linha"
            ></div>

        </div>

        <div class="hist-card hist-card-largo">

            <div class="hist-card-titulo">
                LINHA JOSÉ JÚLIO — VAZÃO
            </div>

            <div class="hist-card-unidade">
                m³/s
            </div>

            <div
                class="hist-metricas"
                id="hist-metricas-vazao"
            ></div>

            <div
                class="hist-svg-wrap"
                id="grafico-vazao"
            ></div>

        </div>

    </div>

    <div class="hist-rodape">
        Fonte: histórico coletado pelo Monitor Taquari.
        Os gráficos representam dados observados disponíveis.
    </div>

</section>

<div
    id="hist-tooltip"
    class="hist-tooltip"
></div>

<script>

(function () {

const DADOS =
""" + payload + """;

let HORAS = 24;

function numeroBR(
    valor,
    casas
) {

    if (
        valor === null
        || valor === undefined
        || !Number.isFinite(
            Number(valor)
        )
    ) {
        return "-";
    }

    return Number(
        valor
    ).toLocaleString(
        "pt-BR",
        {
            minimumFractionDigits: casas,
            maximumFractionDigits: casas
        }
    );
}


function filtrar(
    serie
) {

    if (
        !serie
        || !serie.length
    ) {
        return [];
    }

    const ultimo =
        new Date(
            serie[
                serie.length - 1
            ].t
        );

    const limite =
        new Date(
            ultimo.getTime()
            - HORAS
            * 60
            * 60
            * 1000
        );

    return serie.filter(
        p =>
            new Date(
                p.t
            ) >= limite
    );
}


function metricas(
    serie,
    unidade,
    casas
) {

    if (!serie.length) {

        return {
            html:
                '<div class="hist-sem-dados">'
                + 'Sem dados neste período.'
                + '</div>'
        };
    }

    const valores =
        serie.map(
            p => Number(
                p.v
            )
        );

    const atual =
        valores[
            valores.length - 1
        ];

    const inicial =
        valores[0];

    const maximo =
        Math.max(
            ...valores
        );

    const minimo =
        Math.min(
            ...valores
        );

    const variacao =
        atual - inicial;

    const sinal =
        variacao > 0
        ? "+"
        : "";

    return {
        html:
            `
            <div class="hist-metrica">
                <span>Atual</span>
                <strong>
                    ${numeroBR(atual, casas)}
                    ${unidade}
                </strong>
            </div>

            <div class="hist-metrica">
                <span>Máximo</span>
                <strong>
                    ${numeroBR(maximo, casas)}
                    ${unidade}
                </strong>
            </div>

            <div class="hist-metrica">
                <span>Mínimo</span>
                <strong>
                    ${numeroBR(minimo, casas)}
                    ${unidade}
                </strong>
            </div>

            <div class="hist-metrica">
                <span>Variação</span>
                <strong>
                    ${sinal}${numeroBR(variacao, casas)}
                    ${unidade}
                </strong>
            </div>
            `
    };
}


function desenhar(
    destinoId,
    metricasId,
    serieOriginal,
    unidade,
    casas
) {

    const destino =
        document.getElementById(
            destinoId
        );

    const boxMetricas =
        document.getElementById(
            metricasId
        );

    if (
        !destino
        || !boxMetricas
    ) {
        return;
    }

    const serie =
        filtrar(
            serieOriginal
        );

    const resumo =
        metricas(
            serie,
            unidade,
            casas
        );

    boxMetricas.innerHTML =
        resumo.html;

    if (
        serie.length < 2
    ) {

        destino.innerHTML =
            '<div class="hist-sem-dados">'
            + 'Sem histórico suficiente '
            + 'para este período.'
            + '</div>';

        return;
    }

    const largura = 1000;
    const altura = 245;

    const margem = {
        esquerda:58,
        direita:18,
        topo:16,
        baixo:35
    };

    const plotW =
        largura
        - margem.esquerda
        - margem.direita;

    const plotH =
        altura
        - margem.topo
        - margem.baixo;

    const valores =
        serie.map(
            p => Number(
                p.v
            )
        );

    let min =
        Math.min(
            ...valores
        );

    let max =
        Math.max(
            ...valores
        );

    if (max === min) {
        max += 1;
        min -= 1;
    }

    const folga =
        (max - min)
        * 0.12;

    max += folga;
    min -= folga;

    function x(i) {

        if (
            serie.length <= 1
        ) {
            return margem.esquerda;
        }

        return (
            margem.esquerda
            + (
                i
                / (
                    serie.length - 1
                )
            )
            * plotW
        );
    }

    function y(v) {

        return (
            margem.topo
            + (
                (
                    max - v
                )
                / (
                    max - min
                )
            )
            * plotH
        );
    }

    const pontos =
        serie.map(
            (p, i) =>
                `${x(i)},${y(Number(p.v))}`
        ).join(
            " "
        );

    const area =
        `${margem.esquerda},`
        + `${margem.topo + plotH} `
        + pontos
        + ` `
        + `${margem.esquerda + plotW},`
        + `${margem.topo + plotH}`;

    let linhasGrid = "";
    let labelsY = "";

    for (
        let i = 0;
        i <= 4;
        i++
    ) {

        const yy =
            margem.topo
            + (
                i / 4
            )
            * plotH;

        const valor =
            max
            - (
                i / 4
            )
            * (
                max - min
            );

        linhasGrid +=
            `<line
                class="hist-gridline"
                x1="${margem.esquerda}"
                y1="${yy}"
                x2="${margem.esquerda + plotW}"
                y2="${yy}"
            />`;

        labelsY +=
            `<text
                class="hist-eixo-label"
                x="${margem.esquerda - 8}"
                y="${yy + 4}"
                text-anchor="end"
            >
                ${numeroBR(valor, casas)}
            </text>`;
    }

    let labelsX = "";

    const qtdLabels =
        Math.min(
            5,
            serie.length
        );

    for (
        let i = 0;
        i < qtdLabels;
        i++
    ) {

        const indice =
            Math.round(
                (
                    i
                    / (
                        qtdLabels - 1
                    )
                )
                * (
                    serie.length - 1
                )
            );

        const p =
            serie[indice];

        const dt =
            new Date(
                p.t
            );

        const label =
            dt.toLocaleString(
                "pt-BR",
                {
                    day:"2-digit",
                    month:"2-digit",
                    hour:"2-digit",
                    minute:"2-digit"
                }
            );

        labelsX +=
            `<text
                class="hist-eixo-label"
                x="${x(indice)}"
                y="${altura - 8}"
                text-anchor="${
                    i === 0
                    ? "start"
                    : (
                        i === qtdLabels - 1
                        ? "end"
                        : "middle"
                    )
                }"
            >
                ${label}
            </text>`;
    }

    const circles =
        serie.map(
            (p, i) =>
                `<circle
                    cx="${x(i)}"
                    cy="${y(Number(p.v))}"
                    r="7"
                    fill="transparent"
                    data-index="${i}"
                    class="hist-hover-point"
                />`
        ).join("");

    destino.innerHTML =
        `<svg
            class="hist-svg"
            viewBox="0 0 ${largura} ${altura}"
            preserveAspectRatio="none"
        >

            ${linhasGrid}

            ${labelsY}

            ${labelsX}

            <polygon
                class="hist-area"
                points="${area}"
            ></polygon>

            <polyline
                class="hist-linha"
                points="${pontos}"
            ></polyline>

            <circle
                class="hist-ponto-final"
                cx="${x(serie.length - 1)}"
                cy="${
                    y(
                        Number(
                            serie[
                                serie.length - 1
                            ].v
                        )
                    )
                }"
                r="4"
            ></circle>

            ${circles}

        </svg>`;

    const tooltip =
        document.getElementById(
            "hist-tooltip"
        );

    destino
        .querySelectorAll(
            ".hist-hover-point"
        )
        .forEach(
            el => {

                el.addEventListener(
                    "mousemove",
                    evento => {

                        const indice =
                            Number(
                                el.dataset.index
                            );

                        const p =
                            serie[indice];

                        tooltip.innerHTML =
                            `<strong>
                                ${numeroBR(p.v, casas)}
                                ${unidade}
                            </strong>
                            <br>
                            ${p.rotulo}`;

                        tooltip.style.left =
                            (
                                evento.clientX
                                + 14
                            )
                            + "px";

                        tooltip.style.top =
                            (
                                evento.clientY
                                + 14
                            )
                            + "px";

                        tooltip.style.display =
                            "block";
                    }
                );

                el.addEventListener(
                    "mouseleave",
                    () => {

                        tooltip.style.display =
                            "none";
                    }
                );
            }
        );
}


function renderizar() {

    desenhar(
        "grafico-santa",
        "hist-metricas-santa",
        DADOS.series.santa_nivel,
        "m",
        2
    );

    desenhar(
        "grafico-linha",
        "hist-metricas-linha",
        DADOS.series.linha_nivel,
        "m",
        2
    );

    desenhar(
        "grafico-vazao",
        "hist-metricas-vazao",
        DADOS.series.linha_vazao,
        "m³/s",
        0
    );
}


document
    .querySelectorAll(
        ".hist-btn"
    )
    .forEach(
        botao => {

            botao.addEventListener(
                "click",
                () => {

                    HORAS =
                        Number(
                            botao.dataset.horas
                        );

                    document
                        .querySelectorAll(
                            ".hist-btn"
                        )
                        .forEach(
                            b =>
                                b.classList.remove(
                                    "ativo"
                                )
                        );

                    botao.classList.add(
                        "ativo"
                    );

                    renderizar();
                }
            );
        }
    );


renderizar();

})();

</script>
"""


if __name__ == "__main__":

    d = preparar_series()

    print(
        json.dumps(
            {
                "ok": d.get(
                    "ok"
                ),
                "ultima_data": d.get(
                    "ultima_data"
                ),
                "quantidades": {
                    chave: len(
                        valor
                    )
                    for chave, valor
                    in d.get(
                        "series",
                        {}
                    ).items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
