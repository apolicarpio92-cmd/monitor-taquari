from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import libsql


BASE_DIR = Path(__file__).resolve().parent

ARQUIVOS_PERSISTENTES = [
    BASE_DIR / "historico" / "telemetria_historico.csv",
    BASE_DIR / "historico" / "barragens_historico.csv",
    BASE_DIR / "dados" / "status.json",
]


_ESTADO = {
    "configurado": False,
    "conectado": False,
    "ultima_operacao": None,
    "ultima_sincronizacao": None,
    "ultimo_erro": None,
    "quantidade": 0,
    "arquivos": [],
}


def agora():
    return datetime.now().isoformat(
        timespec="seconds"
    )


def turso_configurado():

    ok = bool(
        os.environ.get("TURSO_DATABASE_URL")
        and os.environ.get("TURSO_AUTH_TOKEN")
    )

    _ESTADO["configurado"] = ok

    return ok


def conectar():

    url = os.environ.get(
        "TURSO_DATABASE_URL"
    )

    token = os.environ.get(
        "TURSO_AUTH_TOKEN"
    )

    if not url or not token:

        raise RuntimeError(
            "TURSO_DATABASE_URL ou TURSO_AUTH_TOKEN ausente."
        )

    return libsql.connect(
        str(
            BASE_DIR
            / "monitor_turso_cache.db"
        ),
        sync_url=url,
        auth_token=token,
    )


def criar_tabela(conn):

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitor_arquivos (
            nome TEXT PRIMARY KEY,
            conteudo TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )

    conn.commit()


def atualizar_lista_local(conn):

    rows = conn.execute(
        """
        SELECT
            nome,
            atualizado_em,
            length(conteudo)
        FROM monitor_arquivos
        ORDER BY nome
        """
    ).fetchall()

    arquivos = []

    for nome, atualizado_em, tamanho in rows:

        arquivos.append(
            {
                "nome": nome,
                "atualizado_em": atualizado_em,
                "bytes": tamanho,
            }
        )

    _ESTADO["quantidade"] = len(
        arquivos
    )

    _ESTADO["arquivos"] = arquivos


def inicializar():

    _ESTADO["ultima_operacao"] = (
        "inicializacao"
    )

    if not turso_configurado():

        _ESTADO["conectado"] = False
        _ESTADO["ultimo_erro"] = (
            "Credenciais nao configuradas."
        )

        print(
            "[TURSO] Credenciais nao configuradas.",
            flush=True,
        )

        return False

    conn = None

    try:

        conn = conectar()

        criar_tabela(
            conn
        )

        # sincronizacao remota
        conn.sync()

        atualizar_lista_local(
            conn
        )

        _ESTADO["conectado"] = True
        _ESTADO["ultima_sincronizacao"] = agora()
        _ESTADO["ultimo_erro"] = None

        print(
            "[TURSO] Banco inicializado.",
            flush=True,
        )

        return True

    except Exception as e:

        _ESTADO["conectado"] = False
        _ESTADO["ultimo_erro"] = str(e)

        raise

    finally:

        if conn is not None:
            conn.close()


def salvar_no_turso():

    _ESTADO["ultima_operacao"] = (
        "salvamento"
    )

    if not turso_configurado():
        return False

    conn = None

    try:

        conn = conectar()

        criar_tabela(
            conn
        )

        momento = agora()

        total = 0

        for arquivo in ARQUIVOS_PERSISTENTES:

            if not arquivo.exists():
                continue

            conteudo = arquivo.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )

            nome = str(
                arquivo.relative_to(
                    BASE_DIR
                )
            ).replace(
                "\\",
                "/",
            )

            conn.execute(
                """
                INSERT INTO monitor_arquivos
                    (
                        nome,
                        conteudo,
                        atualizado_em
                    )
                VALUES (?, ?, ?)

                ON CONFLICT(nome)
                DO UPDATE SET
                    conteudo = excluded.conteudo,
                    atualizado_em = excluded.atualizado_em
                """,
                (
                    nome,
                    conteudo,
                    momento,
                ),
            )

            total += 1

        conn.commit()

        # envia as alteracoes para Turso
        conn.sync()

        atualizar_lista_local(
            conn
        )

        _ESTADO["conectado"] = True
        _ESTADO["ultima_sincronizacao"] = agora()
        _ESTADO["ultimo_erro"] = None

        print(
            f"[TURSO] {total} arquivo(s) sincronizado(s).",
            flush=True,
        )

        return True

    except Exception as e:

        _ESTADO["conectado"] = False
        _ESTADO["ultimo_erro"] = str(e)

        raise

    finally:

        if conn is not None:
            conn.close()


def restaurar_do_turso():

    _ESTADO["ultima_operacao"] = (
        "restauracao"
    )

    if not turso_configurado():
        return False

    conn = None

    try:

        conn = conectar()

        # recebe o estado remoto
        conn.sync()

        criar_tabela(
            conn
        )

        rows = conn.execute(
            """
            SELECT
                nome,
                conteudo
            FROM monitor_arquivos
            """
        ).fetchall()

        total = 0

        for nome, conteudo in rows:

            destino = (
                BASE_DIR
                / Path(nome)
            )

            destino.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            destino.write_text(
                conteudo,
                encoding="utf-8",
            )

            total += 1

        atualizar_lista_local(
            conn
        )

        _ESTADO["conectado"] = True
        _ESTADO["ultima_sincronizacao"] = agora()
        _ESTADO["ultimo_erro"] = None

        print(
            f"[TURSO] {total} arquivo(s) restaurado(s).",
            flush=True,
        )

        return True

    except Exception as e:

        _ESTADO["conectado"] = False
        _ESTADO["ultimo_erro"] = str(e)

        raise

    finally:

        if conn is not None:
            conn.close()


def status_turso():
    """
    IMPORTANTE:
    esta funcao NAO acessa a rede.

    Ela devolve somente o resultado da ultima
    operacao Turso executada pelo monitor.
    Por isso /turso-status responde imediatamente.
    """

    return {
        "configurado": turso_configurado(),
        "conectado": _ESTADO[
            "conectado"
        ],
        "ultima_operacao": _ESTADO[
            "ultima_operacao"
        ],
        "ultima_sincronizacao": _ESTADO[
            "ultima_sincronizacao"
        ],
        "ultimo_erro": _ESTADO[
            "ultimo_erro"
        ],
        "quantidade": _ESTADO[
            "quantidade"
        ],
        "arquivos": list(
            _ESTADO[
                "arquivos"
            ]
        ),
    }
