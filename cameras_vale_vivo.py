CAMERAS = [
    {
        "id": "18",
        "nome": "Santa Tereza",
        "youtube_url": (
            "https://www.youtube.com/watch"
            "?v=lO27uwIzIKE"
            "&source_ve_path=MTc4NDI0"
        ),
        "titulo": "Início do Rio Taquari",
        "descricao": "Encontro dos rios Antas e Carreiro",
        "status": "ao_vivo",
        "video_id": "lO27uwIzIKE",
    },
    {
        "id": "3",
        "nome": "Encantado / Muçum",
        "titulo": "Ponte da ERS-129",
        "descricao": (
            "Vista entre Encantado e Muçum"
        ),
        "status": "ao_vivo",
        "video_id": "ocb4Nti4a0k",
        "pagina": (
            "https://valevivo.app/"
            "camera-ao-vivo/"
            "camera-teste-lajeado-encantado/"
        ),
    },
    {
        "id": "13",
        "nome": "Roca Sales",
        "titulo": "Ponte do Rio Taquari",
        "descricao": (
            "Vista do Rio Taquari e da ponte da ERS-129"
        ),
        "status": "ao_vivo",
        "video_id": "3gOSQGMX76M",
        "pagina": (
            "https://www.youtube.com/watch"
            "?v=3gOSQGMX76M"
        ),
    },
    {
        "id": "17",
        "nome": "Colinas",
        "titulo": "Rio Taquari em Colinas",
        "descricao": "Vista da ERS-129 e do Rio Taquari",
        "status": "listada_ao_vivo",
    },
    {
        "id": "5",
        "nome": "Cruzeiro / Estrela",
        "titulo": "Rio Taquari em Cruzeiro do Sul",
        "descricao": "Vista para o Rio Taquari e Estrela",
        "status": "listada_ao_vivo",
    },
]


CENTRAL_URL = (
    "https://valevivo.app/cameras-ao-vivo/"
)


def coletar_cameras_vale_vivo(
    forcar=False,
):

    dados = []

    for camera in CAMERAS:

        item = dict(
            camera
        )

        if "video_id" not in item:
            item["video_id"] = None

        item["pagina"] = (
            CENTRAL_URL
        )

        item["fonte"] = (
            "Vale Vivo 24h"
        )

        item["observacao"] = (
            "Câmera listada na central pública do Vale Vivo."
        )

        dados.append(
            item
        )

    return dados


def testar():

    print()
    print("=" * 70)
    print("CAMERAS VALE VIVO")
    print("=" * 70)

    for item in coletar_cameras_vale_vivo():

        print()
        print(
            f"#{item['id']} - "
            f"{item['nome']}"
        )

        print(
            "Status....:",
            item["status"]
        )

        print(
            "Central...:",
            item["pagina"]
        )

        print(
            "Video ID..:",
            "-"
        )


if __name__ == "__main__":
    testar()
