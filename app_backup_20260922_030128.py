import os
import threading
import time
import traceback
from pathlib import Path

from flask import Flask, send_file, jsonify

import monitor_cloud

from turso_storage import (
    inicializar,
    restaurar_do_turso,
    salvar_no_turso,
)


BASE = Path(__file__).resolve().parent

app = Flask(__name__)

INTERVALO = 300

_lock = threading.Lock()
_coletor_iniciado = False


def coletor():

    print(
        "[CLOUD] Coletor iniciado.",
        flush=True
    )

    while True:

        try:

            print(
                "[CLOUD] Executando ciclo...",
                flush=True
            )

            monitor_cloud.ciclo()

            print(
                "[CLOUD] Ciclo concluido.",
                flush=True
            )

            try:

                salvar_no_turso()

            except Exception:

                print(
                    "[TURSO] ERRO AO SINCRONIZAR:",
                    flush=True
                )

                traceback.print_exc()

        except Exception:

            print(
                "[CLOUD] ERRO NO CICLO:",
                flush=True
            )

            traceback.print_exc()

        time.sleep(
            INTERVALO
        )


def iniciar_coletor():

    global _coletor_iniciado

    with _lock:

        if _coletor_iniciado:
            return

        t = threading.Thread(
            target=coletor,
            daemon=True,
            name="coletor-taquari",
        )

        t.start()

        _coletor_iniciado = True


# ============================================================
# TURSO
# ============================================================

try:

    inicializar()

    restaurar_do_turso()

except Exception:

    print(
        "[TURSO] ERRO NA INICIALIZACAO:",
        flush=True
    )

    traceback.print_exc()


# ============================================================
# COLETOR
# ============================================================

iniciar_coletor()


@app.get("/")
def dashboard():

    arquivo = (
        BASE
        / "dashboard_v3.html"
    )

    if not arquivo.exists():

        return (
            "Dashboard ainda nao foi gerado.",
            503
        )

    return send_file(
        arquivo,
        mimetype="text/html"
    )


@app.get("/health")
def health():

    return jsonify(
        {
            "status": "ok",
            "monitor": "taquari",
            "turso": bool(
                os.environ.get(
                    "TURSO_DATABASE_URL"
                )
            ),
        }
    )


@app.get("/status")
def status():

    arquivo = (
        BASE
        / "dados"
        / "status.json"
    )

    if not arquivo.exists():

        return jsonify(
            {
                "status": "sem_dados"
            }
        )

    return send_file(
        arquivo,
        mimetype="application/json"
    )


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
