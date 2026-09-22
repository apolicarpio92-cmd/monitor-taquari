import os
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    send_file,
)

# ============================================================
# FUSO HORARIO BRASIL
# ============================================================

os.environ["TZ"] = "America/Sao_Paulo"

if hasattr(time, "tzset"):
    time.tzset()


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

INICIO_PROCESSO = datetime.now()

ESTADO_RUNTIME = {
    "ciclo_em_execucao": False,
    "ultimo_ciclo_inicio": None,
    "ultima_coleta_ok": None,
    "ultimo_erro": None,
    "ultimo_erro_em": None,
    "ultimo_ping_externo": None,
}


def agora_iso():
    return datetime.now().isoformat(
        timespec="seconds"
    )


# ============================================================
# COLETOR
# ============================================================

def coletor():

    print(
        "[CLOUD] Coletor iniciado.",
        flush=True,
    )

    while True:

        ESTADO_RUNTIME[
            "ciclo_em_execucao"
        ] = True

        ESTADO_RUNTIME[
            "ultimo_ciclo_inicio"
        ] = agora_iso()

        try:

            print(
                "[CLOUD] Executando ciclo...",
                flush=True,
            )

            monitor_cloud.ciclo()

            ESTADO_RUNTIME[
                "ultima_coleta_ok"
            ] = agora_iso()

            ESTADO_RUNTIME[
                "ultimo_erro"
            ] = None

            ESTADO_RUNTIME[
                "ultimo_erro_em"
            ] = None

            print(
                "[CLOUD] Ciclo concluido.",
                flush=True,
            )

            try:

                salvar_no_turso()

            except Exception as e:

                ESTADO_RUNTIME[
                    "ultimo_erro"
                ] = (
                    "Turso: "
                    + str(e)
                )

                ESTADO_RUNTIME[
                    "ultimo_erro_em"
                ] = agora_iso()

                print(
                    "[TURSO] Erro ao salvar historico.",
                    flush=True,
                )

                traceback.print_exc()

        except Exception as e:

            ESTADO_RUNTIME[
                "ultimo_erro"
            ] = str(e)

            ESTADO_RUNTIME[
                "ultimo_erro_em"
            ] = agora_iso()

            print(
                "[CLOUD] ERRO NO CICLO:",
                flush=True,
            )

            traceback.print_exc()

        finally:

            ESTADO_RUNTIME[
                "ciclo_em_execucao"
            ] = False

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
# INICIA COLETOR
# ============================================================

iniciar_coletor()


# ============================================================
# WIDGET INJETADO NO DASHBOARD
# ============================================================

WIDGET_STATUS = r'''
<style>
#runtime-monitor-taquari {
    position: fixed;
    right: 16px;
    bottom: 16px;
    z-index: 99999;
    min-width: 250px;
    max-width: 340px;
    padding: 12px 14px;
    border-radius: 12px;
    background: rgba(20, 24, 18, .94);
    color: #f4f6ef;
    font-family: Arial, sans-serif;
    font-size: 12px;
    line-height: 1.45;
    box-shadow: 0 4px 18px rgba(0,0,0,.25);
    border: 1px solid rgba(255,255,255,.12);
}

#runtime-monitor-taquari .rt-titulo {
    font-weight: 700;
    font-size: 13px;
    margin-bottom: 5px;
}

#runtime-monitor-taquari .rt-ok {
    color: #9be17c;
    font-weight: 700;
}

#runtime-monitor-taquari .rt-atencao {
    color: #ffd166;
    font-weight: 700;
}

#runtime-monitor-taquari .rt-erro {
    color: #ff8080;
    font-weight: 700;
}

#runtime-monitor-taquari .rt-secundario {
    opacity: .78;
}

@media (max-width: 700px) {
    #runtime-monitor-taquari {
        left: 10px;
        right: 10px;
        bottom: 10px;
        max-width: none;
        min-width: 0;
    }
}
</style>

<div id="runtime-monitor-taquari">
    <div class="rt-titulo">
        Status do servidor
    </div>

    <div id="rt-status">
        Consultando...
    </div>

    <div
        id="rt-coleta"
        class="rt-secundario"
    >
        Última coleta: -
    </div>

    <div
        id="rt-ping"
        class="rt-secundario"
    >
        Último ping externo: -
    </div>
</div>

<script>
(function () {

    const elStatus =
        document.getElementById(
            "rt-status"
        );

    const elColeta =
        document.getElementById(
            "rt-coleta"
        );

    const elPing =
        document.getElementById(
            "rt-ping"
        );

    function minutosDesde(iso) {

        if (!iso) {
            return null;
        }

        const data =
            new Date(iso);

        if (isNaN(data.getTime())) {
            return null;
        }

        const diff =
            Date.now()
            - data.getTime();

        return Math.max(
            0,
            Math.floor(
                diff / 60000
            )
        );
    }

    function formatarHora(iso) {

        if (!iso) {
            return "-";
        }

        const d =
            new Date(iso);

        if (isNaN(d.getTime())) {
            return iso;
        }

        return d.toLocaleString(
            "pt-BR",
            {
                timeZone:
                    "America/Sao_Paulo",
                hour12: false
            }
        );
    }

    async function atualizarRuntime() {

        try {

            const resposta =
                await fetch(
                    "/runtime-status?ts="
                    + Date.now(),
                    {
                        cache: "no-store"
                    }
                );

            if (!resposta.ok) {
                throw new Error(
                    "HTTP "
                    + resposta.status
                );
            }

            const dados =
                await resposta.json();

            const minutos =
                minutosDesde(
                    dados.ultima_coleta_ok
                );

            if (
                dados.ciclo_em_execucao
            ) {

                elStatus.innerHTML =
                    '<span class="rt-atencao">'
                    + '● COLETA EM ANDAMENTO'
                    + '</span>';

            }
            else if (
                minutos !== null
                && minutos <= 10
            ) {

                elStatus.innerHTML =
                    '<span class="rt-ok">'
                    + '● SERVIDOR ATIVO'
                    + '</span>';

            }
            else if (
                minutos !== null
                && minutos <= 20
            ) {

                elStatus.innerHTML =
                    '<span class="rt-atencao">'
                    + '● COLETA ATRASADA'
                    + '</span>';

            }
            else {

                elStatus.innerHTML =
                    '<span class="rt-erro">'
                    + '● SEM COLETA RECENTE'
                    + '</span>';

            }

            let texto =
                "Última coleta: "
                + formatarHora(
                    dados.ultima_coleta_ok
                );

            if (minutos !== null) {

                texto +=
                    " · há "
                    + minutos
                    + " min";
            }

            elColeta.textContent =
                texto;

            const minutosPing =
                dados.minutos_desde_ping;

            let textoPing =
                "Último ping externo: "
                + formatarHora(
                    dados.ultimo_ping_externo
                );

            if (
                minutosPing !== null
                && minutosPing !== undefined
            ) {

                textoPing +=
                    " · há "
                    + minutosPing
                    + " min";
            }

            elPing.textContent =
                textoPing;

            if (dados.ultimo_erro) {

                elStatus.innerHTML +=
                    '<div class="rt-erro" '
                    + 'style="margin-top:4px">'
                    + 'Último erro registrado'
                    + '</div>';
            }

        }
        catch (erro) {

            elStatus.innerHTML =
                '<span class="rt-erro">'
                + '● SERVIDOR INDISPONÍVEL'
                + '</span>';

            elColeta.textContent =
                "Não foi possível consultar "
                + "o status do servidor.";
        }
    }

    atualizarRuntime();

    setInterval(
        atualizarRuntime,
        30000
    );

})();
</script>
'''


# ============================================================
# ROTAS
# ============================================================

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

    html = arquivo.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if "</body>" in html:

        html = html.replace(
            "</body>",
            WIDGET_STATUS
            + "\n</body>",
            1,
        )

    else:

        html += WIDGET_STATUS

    resposta = Response(
        html,
        mimetype="text/html",
    )

    resposta.headers[
        "Cache-Control"
    ] = (
        "no-store, no-cache, "
        "must-revalidate, max-age=0"
    )

    resposta.headers[
        "Pragma"
    ] = "no-cache"

    resposta.headers[
        "Expires"
    ] = "0"

    return resposta


@app.get("/ping")
def ping():

    momento = agora_iso()

    ESTADO_RUNTIME[
        "ultimo_ping_externo"
    ] = momento

    return jsonify(
        {
            "status": "ok",
            "monitor": "taquari",
            "hora": momento,
            "ping_registrado": True,
        }
    )

@app.get("/runtime-status")
def runtime_status():

    agora = datetime.now()

    ultima = (
        ESTADO_RUNTIME.get(
            "ultima_coleta_ok"
        )
    )

    minutos = None

    if ultima:

        try:

            dt_ultima = (
                datetime.fromisoformat(
                    ultima
                )
            )

            minutos = int(
                (
                    agora
                    - dt_ultima
                ).total_seconds()
                / 60
            )

        except Exception:

            minutos = None

    uptime_segundos = int(
        (
            agora
            - INICIO_PROCESSO
        ).total_seconds()
    )

    ultimo_ping = ESTADO_RUNTIME.get(
        "ultimo_ping_externo"
    )

    minutos_ping = None

    if ultimo_ping:

        try:

            dt_ping = datetime.fromisoformat(
                ultimo_ping
            )

            minutos_ping = int(
                (
                    agora
                    - dt_ping
                ).total_seconds()
                / 60
            )

        except Exception:

            minutos_ping = None

    return jsonify(
        {
            "status": "ok",
            "ciclo_em_execucao":
                ESTADO_RUNTIME[
                    "ciclo_em_execucao"
                ],
            "ultimo_ciclo_inicio":
                ESTADO_RUNTIME[
                    "ultimo_ciclo_inicio"
                ],
            "ultima_coleta_ok":
                ESTADO_RUNTIME[
                    "ultima_coleta_ok"
                ],
            "minutos_desde_coleta":
                minutos,
            "ultimo_erro":
                ESTADO_RUNTIME[
                    "ultimo_erro"
                ],
            "ultimo_erro_em":
                ESTADO_RUNTIME[
                    "ultimo_erro_em"
                ],
            "uptime_segundos":
                uptime_segundos,
            "ultimo_ping_externo":
                ultimo_ping,
            "minutos_desde_ping":
                minutos_ping,
        }
    )


@app.get("/health")
def health():

    return jsonify(
        {
            "status": "ok",
            "monitor": "taquari",
            "turso":
                turso_configurado(),
            "ultima_coleta":
                ESTADO_RUNTIME[
                    "ultima_coleta_ok"
                ],
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

