from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests


STAC_URL = "https://stac.dataspace.copernicus.eu/v1"

TIMEOUT = (5, 15)


PONTOS = {
    "Cabeceiras / Vacaria": {
        "lat": -28.500000,
        "lon": -50.950000,
    },
    "Barra Mansa": {
        "lat": -29.169724,
        "lon": -51.741165,
    },
    "Santa Tereza": {
        "lat": -29.178100,
        "lon": -51.732200,
    },
}


def _satellite_from_id(scene_id: str) -> str:

    if scene_id.startswith("S2A_"):
        return "Sentinel-2A"

    if scene_id.startswith("S2B_"):
        return "Sentinel-2B"

    if scene_id.startswith("S2C_"):
        return "Sentinel-2C"

    return "Sentinel-2"


def _converter_data(valor):

    if not valor:
        return None

    try:

        return datetime.fromisoformat(
            valor.replace(
                "Z",
                "+00:00",
            )
        )

    except Exception:
        return None


def buscar_cenas(
    lat,
    lon,
    dias=60,
):

    agora = datetime.now(
        timezone.utc
    )

    inicio = (
        agora
        - timedelta(
            days=dias
        )
    )

    margem = 0.020

    body = {
        "collections": [
            "sentinel-2-l2a"
        ],
        "bbox": [
            lon - margem,
            lat - margem,
            lon + margem,
            lat + margem,
        ],
        "datetime": (
            inicio.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            + "/"
            + agora.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        ),
        "limit": 20,
        "query": {
            "eo:cloud_cover": {
                "lt": 90
            }
        },
        "sortby": [
            {
                "field":
                    "properties.datetime",
                "direction":
                    "desc",
            }
        ],
    }

    resposta = requests.post(
        STAC_URL + "/search",
        json=body,
        timeout=TIMEOUT,
        headers={
            "User-Agent":
                "Monitor-Taquari/1.0"
        },
    )

    resposta.raise_for_status()

    payload = resposta.json()

    return payload.get(
        "features",
        [],
    )


def escolher_cena(
    features,
):

    if not features:
        return None

    cenas = []

    for feature in features:

        props = feature.get(
            "properties",
            {},
        )

        assets = feature.get(
            "assets",
            {},
        )

        nuvens = props.get(
            "eo:cloud_cover"
        )

        try:
            nuvens = float(nuvens)
        except Exception:
            nuvens = 999.0

        data = _converter_data(
            props.get(
                "datetime"
            )
        )

        thumbnail = None

        thumb = assets.get(
            "thumbnail"
        )

        if isinstance(
            thumb,
            dict,
        ):
            thumbnail = thumb.get(
                "href"
            )

        cenas.append(
            {
                "id":
                    feature.get(
                        "id",
                        "",
                    ),
                "data":
                    data,
                "nuvens":
                    nuvens,
                "thumbnail":
                    thumbnail,
            }
        )

    # --------------------------------------------------------
    # Regra:
    # 1) tenta cena <= 20% nuvens
    # 2) depois <= 40%
    # 3) senao pega a mais recente
    # --------------------------------------------------------

    for limite in [
        20,
        40,
        90,
    ]:

        candidatas = [
            c
            for c in cenas
            if (
                c["data"] is not None
                and c["nuvens"] <= limite
            )
        ]

        if candidatas:

            candidatas.sort(
                key=lambda x:
                    x["data"],
                reverse=True,
            )

            escolhida = (
                candidatas[0]
            )

            escolhida[
                "satellite"
            ] = _satellite_from_id(
                escolhida["id"]
            )

            escolhida[
                "criterio_nuvens"
            ] = limite

            return escolhida

    return None


def classificar_cena(
    data,
    nuvens,
):

    agora = datetime.now(
        timezone.utc
    )

    idade_dias = None

    if data is not None:

        try:

            idade_dias = max(
                0,
                (
                    agora
                    - data.astimezone(
                        timezone.utc
                    )
                ).days,
            )

        except Exception:
            idade_dias = None

    # --------------------------------------------------------
    # IDADE
    # --------------------------------------------------------

    if idade_dias is None:

        idade_status = (
            "SEM DATA"
        )

        idade_classe = (
            "neutro"
        )

    elif idade_dias <= 7:

        idade_status = (
            "RECENTE"
        )

        idade_classe = (
            "bom"
        )

    elif idade_dias <= 14:

        idade_status = (
            "ATENÇÃO"
        )

        idade_classe = (
            "atencao"
        )

    else:

        idade_status = (
            "IMAGEM ANTIGA"
        )

        idade_classe = (
            "antigo"
        )

    # --------------------------------------------------------
    # NUVENS
    # --------------------------------------------------------

    try:
        valor_nuvens = float(
            nuvens
        )
    except Exception:
        valor_nuvens = None

    if valor_nuvens is None:

        nuvem_status = (
            "NUVENS DESCONHECIDAS"
        )

        nuvem_classe = (
            "neutro"
        )

    elif valor_nuvens <= 10:

        nuvem_status = (
            "BAIXA NUVEM"
        )

        nuvem_classe = (
            "bom"
        )

    elif valor_nuvens <= 30:

        nuvem_status = (
            "NUVEM MODERADA"
        )

        nuvem_classe = (
            "atencao"
        )

    else:

        nuvem_status = (
            "MUITA NUVEM"
        )

        nuvem_classe = (
            "antigo"
        )

    return {
        "idade_dias":
            idade_dias,

        "idade_status":
            idade_status,

        "idade_classe":
            idade_classe,

        "nuvem_status":
            nuvem_status,

        "nuvem_classe":
            nuvem_classe,
    }


def coletar_imagens_atuais():

    resultado = {}

    for nome, ponto in (
        PONTOS.items()
    ):

        try:

            features = buscar_cenas(
                ponto["lat"],
                ponto["lon"],
            )

            cena = escolher_cena(
                features
            )

            if cena is None:

                resultado[nome] = {
                    "ok": False,
                    "erro":
                        "Nenhuma cena encontrada.",
                }

                continue

            classificacao = (
                classificar_cena(
                    cena["data"],
                    cena["nuvens"],
                )
            )

            resultado[nome] = {
                "ok": True,
                "nome":
                    nome,
                "lat":
                    ponto["lat"],
                "lon":
                    ponto["lon"],
                "id":
                    cena["id"],
                "data":
                    cena["data"],
                "nuvens":
                    cena["nuvens"],
                "thumbnail":
                    cena["thumbnail"],
                "satellite":
                    cena["satellite"],
                "criterio_nuvens":
                    cena[
                        "criterio_nuvens"
                    ],
            }

        except Exception as e:

            resultado[nome] = {
                "ok": False,
                "erro":
                    str(e),
            }

    return resultado


def testar():

    dados = (
        coletar_imagens_atuais()
    )

    for nome, d in (
        dados.items()
    ):

        print()
        print("=" * 60)
        print(nome)

        if not d.get("ok"):

            print(
                "ERRO:",
                d.get("erro"),
            )

            continue

        print(
            "SATELITE:",
            d["satellite"],
        )

        print(
            "DATA:",
            d["data"],
        )

        print(
            "NUVENS:",
            round(
                d["nuvens"],
                1,
            ),
            "%",
        )

        print(
            "ID:",
            d["id"],
        )

        print(
            "THUMB:",
            d["thumbnail"],
        )


if __name__ == "__main__":
    testar()
