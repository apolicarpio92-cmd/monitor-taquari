CAMERAS = [
    {
        "id": "18",
        "nome": "Santa Tereza",
        "titulo": "Início do Rio Taquari",
        "descricao": "Encontro dos rios Antas e Carreiro",
        "status": "listada_ao_vivo",
    },
    {
        "id": "20",
        "nome": "Encantado / Muçum",
        "titulo": "Belvedere para o Rio Taquari",
        "descricao": "Vista da região de Encantado e Muçum",
        "status": "listada_ao_vivo",
    },
    {
        "id": "13",
        "nome": "Roca Sales",
        "titulo": "Ponte do Rio Taquari",
        "descricao": "Vista da ponte e do Rio Taquari",
        "status": "listada_ao_vivo",
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
