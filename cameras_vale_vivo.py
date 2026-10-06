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
            "Vista do Rio Taquari entre Encantado e Muçum"
        ),
        "status": "ao_vivo",
        "video_id": "d7Cc2gil3Hw",
        "pagina": (
            "https://www.youtube.com/watch"
            "?v=d7Cc2gil3Hw"
        ),
    },
    {
        "id": "13",
        "nome": "Roca Sales",
        "titulo": "Ponte do Rio Taquari",
        "descricao": (
            "Vista do Rio Taquari e da ponte em Roca Sales"
        ),
        "status": "ao_vivo",
        "video_id": "dXBkUC6Aqkw",
        "pagina": (
            "https://www.youtube.com/watch"
            "?v=dXBkUC6Aqkw"
        ),
    },
    {
        "id": "17",
        "nome": "Colinas",
        "titulo": "Rio Taquari em Colinas",
        "descricao": (
            "Vista da ERS-129 e do Rio Taquari"
        ),
        "status": "ao_vivo",
        "video_id": "JtZ_JrBeVAY",
        "pagina": (
            "https://www.youtube.com/watch"
            "?v=JtZ_JrBeVAY"
        ),
    },
    {
        "id": "5",
        "nome": "Cruzeiro / Estrela",
        "titulo": "Rio Taquari em Cruzeiro do Sul",
        "descricao": (
            "Vista da Casa do Morro para o Rio Taquari e Estrela"
        ),
        "status": "ao_vivo",
        "video_id": "cP9jwZhv5Fg",
        "pagina": (
            "https://www.youtube.com/watch"
            "?v=cP9jwZhv5Fg"
        ),
    },

    {
        "id": "15",
        "nome": "Bom Retiro do Sul",
        "titulo": "Barragem e Eclusa de Bom Retiro do Sul",
        "descricao": (
            "Vista do Rio Taquari na barragem e eclusa"
        ),
        "status": "ao_vivo",
        "video_id": "dqs6QoKIgqg",
        "pagina": (
            "https://www.youtube.com/watch"
            "?v=dqs6QoKIgqg"
        ),
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
