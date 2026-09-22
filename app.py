import os
import threading
import time
import traceback

# ============================================================
# FUSO HORARIO BRASIL
# ============================================================

os.environ["TZ"] = "America/Sao_Paulo"

if hasattr(time, "tzset"):
    time.tzset()

from pathlib import Path

from flask import Flask, jsonify, send_file

import monitor_cloud

from turso_storage import (
    inicializar,
    restaurar_do_turso,
    salvar_no_turso,
    turso_configurado,
    status_turso,
)


BASE_DIR = Path(__file__).resolve().parent

# ============================================================
# PASTAS DE TRABALHO
# ============================================================

for pasta in (
    BASE_DIR / "logs",
    BASE_DIR / "dados",
    BASE_DIR / "historico",
):
    pasta.mkdir(
        parents=True,
        exist_ok=True,
    )

app = Flask(__name__)

INTERVALO = 300

_lock = threading.Lock()
_coletor_iniciado = False


def coletor():

    print(
        "[CLOUD] Coletor iniciado.",
        flush=True,
    )

    while True:

        try:

            print(
                "[CLOUD] Executando ciclo...",
                flush=True,
            )

            monitor_cloud.ciclo()

            print(
                "[CLOUD] Ciclo concluido.",
                flush=True,
            )

            try:
                salvar_no_turso()

            except Exception:
                print(
                    "[TURSO] Erro ao salvar historico.",
                    flush=True,
                )
                traceback.print_exc()

        except Exception:

            print(
                "[CLOUD] ERRO NO CICLO:",
                flush=True,
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

        thread = threading.Thread(
            target=coletor,
            daemon=True,
            name="coletor-taquari",
        )

        thread.start()

        _coletor_iniciado = True


# ============================================================
# TURSO
# ============================================================

try:

    if turso_configurado():

        inicializar()
        restaurar_do_turso()

    else:

        print(
            "[TURSO] Credenciais nao encontradas.",
            flush=True,
        )

except Exception:

    print(
        "[TURSO] ERRO NA INICIALIZACAO:",
        flush=True,
    )

    traceback.print_exc()


# ============================================================
# COLETOR
# ============================================================

iniciar_coletor()


@app.get("/")
def dashboard():

    arquivo = (
        BASE_DIR
        / "dashboard_v3.html"
    )

    if not arquivo.exists():

        return (
            "Dashboard ainda nao foi gerado.",
            503,
        )

    return send_file(
        arquivo,
        mimetype="text/html",
        max_age=0,
    )


@app.get("/health")
def health():

    return jsonify(
        {
            "status": "ok",
            "monitor": "taquari",
            "turso": turso_configurado(),
        }
    )


@app.get("/turso-status")
def turso_status():

    try:

        resultado = status_turso()

        return jsonify(
            {
                "status": "ok",
                "turso": resultado,
            }
        )

    except Exception as e:

        return jsonify(
            {
                "status": "erro",
                "erro": str(e),
            }
        ), 500

@app.get("/status")
def status():

    arquivo = (
        BASE_DIR
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
        mimetype="application/json",
        max_age=0,
    )


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
    )



