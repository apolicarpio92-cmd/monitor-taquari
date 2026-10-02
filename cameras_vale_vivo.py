import html
import re
import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

import requests


LISTA_URL = (
    "https://valevivo.app/cameras-ao-vivo/"
)

TIMEOUT = (4, 8)

CACHE_SEGUNDOS = 300


# ============================================================
# ULTIMOS PLAYERS CONHECIDOS
#
# Sao fallback.
#
# Se a consulta ao Vale Vivo funcionar e encontrar outro
# player, o ID novo tem prioridade automaticamente.
# ============================================================

CAMERAS = [
    {
        "id": "18",
        "nome": "Santa Tereza",
        "titulo": "Início do Rio Taquari",
        "descricao": (
            "Encontro dos rios Antas e Carreiro"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "18-inicio-do-rio-taquari-"
            "no-encontro-do-carreiro-e-antas/"
        ),
        "video_fallback": "kn1qx5Sin20",
        "status_fallback": "ao_vivo",
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
        "video_fallback": "XXp1Ezu1Dbs",
        "status_fallback": "desconectada",
    },

    {
        "id": "13",
        "nome": "Roca Sales",
        "titulo": "Ponte do Rio Taquari",
        "descricao": (
            "Vista da ponte e do Rio Taquari"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "13-vista-de-arroio-do-meio-"
            "lajeado-estrela-e-teutonia/"
        ),
        "video_fallback": "ddJVi6hsPys",
        "status_fallback": "ao_vivo",
    },

    {
        "id": "17",
        "nome": "Colinas",
        "titulo": "Rio Taquari em Colinas",
        "descricao": (
            "Vista da ERS-129 e do Rio Taquari"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "17-colinas-vista-a-ers-129-"
            "e-ao-rio-taquari/"
        ),
        "video_fallback": "bjvL6vHche0",
        "status_fallback": "ao_vivo",
    },

    {
        "id": "5",
        "nome": "Cruzeiro / Estrela",
        "titulo": (
            "Rio Taquari em Cruzeiro do Sul"
        ),
        "descricao": (
            "Vista para o Rio Taquari e Estrela"
        ),
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "vista-da-casa-do-morro-"
            "para-o-rio-taquari-e-estrela-"
            "camera-em-cruzeiro-do-sul/"
        ),
        "video_fallback": "c7l0qMFBGHs",
        "status_fallback": "ao_vivo",
    },
]


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/154 Safari/537.36"
    ),

    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/xml;q=0.9,"
        "*/*;q=0.8"
    ),

    "Accept-Language": (
        "pt-BR,pt;q=0.9,en;q=0.8"
    ),
}


_CACHE_LOCK = threading.Lock()

_CACHE = {
    "momento": 0.0,
    "dados": None,
}


# ============================================================
# DOWNLOAD
# ============================================================

def _baixar_html(url):

    resposta = requests.get(
        url,
        headers=_HEADERS,
        timeout=TIMEOUT,
    )

    resposta.raise_for_status()

    return resposta.text


# ============================================================
# LIMPA HTML
# ============================================================

def _texto_limpo(
    conteudo,
):

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


# ============================================================
# EXTRAI YOUTUBE
# ============================================================

def _extrair_video_id(
    conteudo,
):

    if not conteudo:
        return None

    conteudo = html.unescape(
        conteudo
    )

    padroes = [
        r"(?:www\.)?youtube\.com/embed/"
        r"([A-Za-z0-9_-]{11})",

        r"(?:www\.)?youtube-nocookie\.com/embed/"
        r"([A-Za-z0-9_-]{11})",

        r"(?:www\.)?youtube\.com/watch\?v="
        r"([A-Za-z0-9_-]{11})",

        r"youtu\.be/"
        r"([A-Za-z0-9_-]{11})",
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


# ============================================================
# STATUS DA LISTAGEM
# ============================================================

def _status_camera(
    html_lista,
    numero,
):

    texto = _texto_limpo(
        html_lista
    )

    if not texto:
        return None

    # Exemplo:
    # "ao vivo #18 INÍCIO..."
    #
    # ou:
    # "desconectada #20 BELVEDERE..."

    padrao = (
        r"(ao\s+vivo|desconectada)"
        r"\s*#\s*"
        + re.escape(
            str(numero)
        )
        + r"\b"
    )

    encontrado = re.search(
        padrao,
        texto,
        flags=re.IGNORECASE,
    )

    if not encontrado:
        return None

    status = (
        encontrado
        .group(1)
        .lower()
        .strip()
    )

    if "desconectada" in status:

        return "desconectada"

    return "ao_vivo"


# ============================================================
# PAGINA INDIVIDUAL
# ============================================================

def _buscar_camera(
    camera,
):

    resultado = dict(
        camera
    )

    resultado.update(
        {
            "video_detectado": None,
            "consulta_ok": False,
            "erro": None,
        }
    )

    try:

        conteudo = _baixar_html(
            camera["pagina"]
        )

        resultado[
            "consulta_ok"
        ] = True

        resultado[
            "video_detectado"
        ] = _extrair_video_id(
            conteudo
        )

    except Exception as exc:

        resultado[
            "erro"
        ] = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return resultado


# ============================================================
# COLETA PRINCIPAL
# ============================================================

def coletar_cameras_vale_vivo(
    forcar=False,
):

    agora = time.monotonic()

    with _CACHE_LOCK:

        cache = _CACHE.get(
            "dados"
        )

        idade = (
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
            and cache is not None
            and idade < CACHE_SEGUNDOS
        ):

            return [
                dict(item)
                for item in cache
            ]

    # --------------------------------------------------------
    # LISTAGEM OFICIAL
    # --------------------------------------------------------

    html_lista = ""

    try:

        html_lista = _baixar_html(
            LISTA_URL
        )

    except Exception as exc:

        print(
            "[VALE VIVO] "
            "Falha na listagem oficial:",
            exc,
            flush=True,
        )

    # --------------------------------------------------------
    # PAGINAS INDIVIDUAIS
    # --------------------------------------------------------

    encontrados = {}

    with ThreadPoolExecutor(
        max_workers=5
    ) as executor:

        futuros = {
            executor.submit(
                _buscar_camera,
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
                    c
                    for c in CAMERAS
                    if c["id"]
                    == camera_id
                )

                item = dict(
                    base
                )

                item.update(
                    {
                        "video_detectado": None,
                        "consulta_ok": False,
                        "erro": str(exc),
                    }
                )

                encontrados[
                    camera_id
                ] = item

    # --------------------------------------------------------
    # DECIDE RESULTADO
    # --------------------------------------------------------

    dados = []

    for camera in CAMERAS:

        item = encontrados.get(
            camera["id"],
            dict(camera),
        )

        video_detectado = (
            item.get(
                "video_detectado"
            )
        )

        video_fallback = (
            camera.get(
                "video_fallback"
            )
        )

        # Player detectado sempre ganha.
        video_id = (
            video_detectado
            or video_fallback
        )

        status_oficial = (
            _status_camera(
                html_lista,
                camera["id"],
            )
        )

        status_fallback = (
            camera.get(
                "status_fallback",
                "indisponivel",
            )
        )

        # Status oficial ganha quando conseguimos ler.
        status = (
            status_oficial
            or status_fallback
        )

        # Se não temos vídeo, não podemos exibir.
        if not video_id:

            status = "indisponivel"

        item[
            "video_id"
        ] = video_id

        item[
            "status"
        ] = status

        item[
            "status_oficial"
        ] = status_oficial

        item[
            "usando_fallback"
        ] = (
            video_detectado is None
            and video_fallback is not None
        )

        dados.append(
            item
        )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

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


# ============================================================
# TESTE
# ============================================================

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
            "Status.........:",
            item.get(
                "status"
            )
        )

        print(
            "Status oficial.:",
            item.get(
                "status_oficial"
            )
            or "-"
        )

        print(
            "Video ID.......:",
            item.get(
                "video_id"
            )
            or "-"
        )

        print(
            "Fallback.......:",
            (
                "SIM"
                if item.get(
                    "usando_fallback"
                )
                else "NAO"
            )
        )

        print(
            "Consulta pagina:",
            (
                "OK"
                if item.get(
                    "consulta_ok"
                )
                else "FALHOU"
            )
        )

        if item.get(
            "erro"
        ):

            print(
                "Erro...........:",
                item["erro"]
            )


if __name__ == "__main__":
    testar()
