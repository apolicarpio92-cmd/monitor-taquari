import html
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


LISTA_URL = (
    "https://valevivo.app/cameras-ao-vivo/"
)

TIMEOUT = (4, 8)

CACHE_SEGUNDOS = 300


CAMERAS = [
    {
        "id": "18",
        "nome": "Santa Tereza",
        "titulo": (
            "Início do Rio Taquari"
        ),
        "descricao": (
            "Encontro dos rios Antas e Carreiro"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "18-inicio-do-rio-taquari-"
            "no-encontro-do-carreiro-e-antas/"
        ),
    },
    {
        "id": "20",
        "nome": "Encantado / Muçum",
        "titulo": (
            "Belvedere para o Rio Taquari"
        ),
        "descricao": (
            "Vista da região de Encantado e Muçum"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "20-belvedere-de-encantado-"
            "para-o-rio-taquari-e-mucum/"
        ),
    },
    {
        "id": "13",
        "nome": "Roca Sales",
        "titulo": (
            "Ponte do Rio Taquari"
        ),
        "descricao": (
            "Vista do Rio Taquari e da ponte em Roca Sales"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "13-vista-de-arroio-do-meio-"
            "lajeado-estrela-e-teutonia/"
        ),
    },
    {
        "id": "17",
        "nome": "Colinas",
        "titulo": (
            "Rio Taquari em Colinas"
        ),
        "descricao": (
            "Vista da ERS-129 e do Rio Taquari"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "17-colinas-vista-a-ers-129-"
            "e-ao-rio-taquari/"
        ),
    },
    {
        "id": "5",
        "nome": "Cruzeiro / Estrela",
        "titulo": (
            "Rio Taquari em Cruzeiro do Sul"
        ),
        "descricao": (
            "Vista da Casa do Morro para o Rio Taquari e Estrela"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "vista-da-casa-do-morro-"
            "para-o-rio-taquari-e-estrela-"
            "camera-em-cruzeiro-do-sul/"
        ),
    },
]


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Monitor Taquari; "
        "+https://monitor-taquari.onrender.com)"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
}


_CACHE_LOCK = threading.Lock()

_CACHE = {
    "momento": 0.0,
    "dados": None,
}


def _baixar_html(url):

    resposta = requests.get(
        url,
        headers=_HEADERS,
        timeout=TIMEOUT,
    )

    resposta.raise_for_status()

    return resposta.text


def _texto_limpo(conteudo):

    if not conteudo:
        return ""

    texto = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        conteudo,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    texto = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        texto,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    texto = re.sub(
        r"<[^>]+>",
        " ",
        texto,
    )

    texto = html.unescape(
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


def _status_camera(
    html_lista,
    numero,
):

    texto = _texto_limpo(
        html_lista
    )

    if not texto:
        return None

    padrao = (
        r"(ao\s+vivo|desconectada)"
        r"\s*#\s*"
        + re.escape(
            str(numero)
        )
        + r"\b"
    )

    achado = re.search(
        padrao,
        texto,
        flags=re.IGNORECASE,
    )

    if not achado:
        return None

    valor = (
        achado
        .group(1)
        .lower()
        .strip()
    )

    if "desconectada" in valor:
        return "desconectada"

    return "ao_vivo"


def _extrair_video_id(
    conteudo,
):

    if not conteudo:
        return None

    conteudo = html.unescape(
        conteudo
    )

    padroes = [
        (
            r"(?:youtube\.com|youtube-nocookie\.com)"
            r"/embed/"
            r"([A-Za-z0-9_-]{6,})"
        ),
        (
            r"youtu\.be/"
            r"([A-Za-z0-9_-]{6,})"
        ),
        (
            r"youtube\.com/watch\?v="
            r"([A-Za-z0-9_-]{6,})"
        ),
    ]

    for padrao in padroes:

        achado = re.search(
            padrao,
            conteudo,
            flags=re.IGNORECASE,
        )

        if achado:

            return achado.group(1)

    return None


def _buscar_pagina_camera(
    camera,
):

    resultado = dict(
        camera
    )

    resultado.update(
        {
            "video_id": None,
            "erro": None,
        }
    )

    try:

        conteudo = _baixar_html(
            camera["pagina"]
        )

        resultado[
            "video_id"
        ] = _extrair_video_id(
            conteudo
        )

    except Exception as exc:

        resultado["erro"] = (
            f"{type(exc).__name__}: {exc}"
        )

    return resultado


def coletar_cameras_vale_vivo(
    forcar=False,
):

    agora = time.monotonic()

    with _CACHE_LOCK:

        dados_cache = (
            _CACHE.get(
                "dados"
            )
        )

        idade_cache = (
            agora
            - float(
                _CACHE.get(
                    "momento",
                    0.0,
                )
            )
        )

        if (
            not forcar
            and dados_cache is not None
            and idade_cache
            < CACHE_SEGUNDOS
        ):

            return [
                dict(item)
                for item
                in dados_cache
            ]

    # --------------------------------------------------------
    # Consulta lista oficial para identificar:
    # AO VIVO / DESCONECTADA
    # --------------------------------------------------------

    try:

        html_lista = _baixar_html(
            LISTA_URL
        )

    except Exception:

        html_lista = ""

    # --------------------------------------------------------
    # As páginas das câmeras são consultadas em paralelo.
    # Assim uma página lenta não segura todas as demais.
    # --------------------------------------------------------

    encontrados = {}

    with ThreadPoolExecutor(
        max_workers=5
    ) as executor:

        futuros = {
            executor.submit(
                _buscar_pagina_camera,
                camera,
            ):
            camera["id"]

            for camera in CAMERAS
        }

        for futuro in as_completed(
            futuros
        ):

            camera_id = (
                futuros[futuro]
            )

            try:

                encontrados[
                    camera_id
                ] = futuro.result()

            except Exception as exc:

                base = next(
                    camera
                    for camera
                    in CAMERAS
                    if camera["id"]
                    == camera_id
                )

                item = dict(
                    base
                )

                item.update(
                    {
                        "video_id": None,
                        "erro": (
                            f"{type(exc).__name__}: {exc}"
                        ),
                    }
                )

                encontrados[
                    camera_id
                ] = item

    dados = []

    for camera in CAMERAS:

        item = encontrados.get(
            camera["id"],
            dict(camera),
        )

        status_oficial = (
            _status_camera(
                html_lista,
                camera["id"],
            )
        )

        video_id = item.get(
            "video_id"
        )

        # ----------------------------------------------------
        # O status da listagem oficial tem prioridade.
        #
        # Se a listagem estiver indisponível, o iframe
        # encontrado serve como indicação de disponibilidade.
        # ----------------------------------------------------

        if (
            status_oficial
            == "desconectada"
        ):

            status = (
                "desconectada"
            )

        elif (
            status_oficial
            == "ao_vivo"
            and video_id
        ):

            status = (
                "ao_vivo"
            )

        elif video_id:

            status = (
                "disponivel"
            )

        else:

            status = (
                "indisponivel"
            )

        item[
            "status"
        ] = status

        item[
            "status_oficial"
        ] = status_oficial

        dados.append(
            item
        )

    with _CACHE_LOCK:

        _CACHE[
            "momento"
        ] = agora

        _CACHE[
            "dados"
        ] = [
            dict(item)
            for item
            in dados
        ]

    return dados


def testar():

    print()
    print(
        "=" * 72
    )

    print(
        "VALE VIVO - CAMERAS"
    )

    print(
        "=" * 72
    )

    dados = (
        coletar_cameras_vale_vivo(
            forcar=True
        )
    )

    for item in dados:

        print()
        print(
            "#"
            + item["id"]
            + " - "
            + item["nome"]
        )

        print(
            "Status.....:",
            item.get(
                "status"
            )
        )

        print(
            "Oficial....:",
            item.get(
                "status_oficial"
            )
        )

        print(
            "Video ID...:",
            item.get(
                "video_id"
            )
            or "-"
        )

        print(
            "Erro.......:",
            item.get(
                "erro"
            )
            or "-"
        )


if __name__ == "__main__":
    testar()
