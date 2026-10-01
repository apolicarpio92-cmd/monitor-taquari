from __future__ import annotations

import json
import sys

import requests


def main():

    if len(sys.argv) != 3:

        print(
            "Uso: ana_http_worker.py URL PARAMS_JSON",
            file=sys.stderr,
            flush=True,
        )

        return 2

    url = sys.argv[1]

    params = json.loads(
        sys.argv[2]
    )

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

        sys.stdout.buffer.write(
            resposta.content
        )

        sys.stdout.buffer.flush()

        return 0

    except Exception as e:

        print(
            (
                type(e).__name__
                + ": "
                + str(e)
            ),
            file=sys.stderr,
            flush=True,
        )

        return 3


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
