# -*- coding: utf-8 -*-
"""
sincronizar.py
==============
Pone al dia la cache local sin volver a descargar el buzon completo.

Que hace:
  1. Pregunta a Gmail que correos existen hoy y con que etiquetas.
  2. De los que ya estan en la cache, actualiza etiquetas, categoria y leido/no leido.
  3. Descarga los metadatos de los que llegaron despues de la ultima descarga.
  4. Borra de la cache los que ya no existen (papelera o eliminados).
  5. Refresca el catalogo de etiquetas.
  6. Regenera datos_gmail.js y el reporte.

Uso:
    python sincronizar.py              # sincroniza y regenera el dashboard
    python sincronizar.py --simular    # solo cuenta las diferencias
"""

import argparse
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_TOKEN = os.path.join(BASE, "token_organizar.json")
RUTA_DB = os.path.join(BASE, "cache_gmail.db")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

CATEGORIAS = {
    "CATEGORY_PERSONAL": 0,
    "CATEGORY_SOCIAL": 1,
    "CATEGORY_PROMOTIONS": 2,
    "CATEGORY_UPDATES": 3,
    "CATEGORY_FORUMS": 4,
}

CABECERAS = ["From", "Subject", "Date", "List-Unsubscribe", "Reply-To"]
CAMPOS = "id,threadId,labelIds,internalDate,sizeEstimate,payload/headers"


def log(t=""):
    print(t, flush=True)


def miles(n):
    return "{:,}".format(n).replace(",", ".")


def autenticar():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(RUTA_TOKEN, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def listar_actuales(svc):
    """id -> lista de etiquetas, de todos los correos que existen hoy."""
    actuales = {}
    token = None
    log("Leyendo el estado actual del buzon...")
    while True:
        r = svc.users().messages().list(
            userId="me", maxResults=500, pageToken=token,
            fields="messages/id,messages/labelIds,nextPageToken",
        ).execute()
        for m in r.get("messages") or []:
            actuales[m["id"]] = list(m.get("labelIds") or [])
        token = r.get("nextPageToken")
        if not token:
            break
        if len(actuales) % 5000 == 0:
            log("  ... %s correos" % miles(len(actuales)))
    log("  %s correos activos (sin contar papelera ni spam)." % miles(len(actuales)))

    # messages.list NO devuelve labelIds (solo id e hilo). Las etiquetas se
    # reconstruyen listando los correos de cada etiqueta, una por una.
    log("Leyendo que etiquetas tiene cada correo...")
    etiquetas = svc.users().labels().list(userId="me").execute().get("labels") or []
    for et in etiquetas:
        lid = et["id"]
        if lid in ("TRASH", "SPAM"):
            continue
        token = None
        while True:
            r = svc.users().messages().list(
                userId="me", labelIds=[lid], maxResults=500, pageToken=token,
                fields="messages/id,nextPageToken",
            ).execute()
            for m in r.get("messages") or []:
                if m["id"] in actuales:
                    actuales[m["id"]].append(lid)
            token = r.get("nextPageToken")
            if not token:
                break
    return actuales


def fila_desde_respuesta(m):
    """Misma conversion que analizar_gmail.py, para no duplicar formatos."""
    import re
    from email.header import decode_header
    from email.utils import parseaddr

    def decodificar(valor):
        if not valor:
            return ""
        try:
            trozos = decode_header(valor)
            salida = []
            for texto, enc in trozos:
                if isinstance(texto, bytes):
                    salida.append(texto.decode(enc or "utf-8", "replace"))
                else:
                    salida.append(texto)
            return "".join(salida)
        except Exception:
            return valor

    def limpiar(t):
        return re.sub(r"\s+", " ", t or "").strip()

    cabeceras = {}
    for h in (m.get("payload") or {}).get("headers") or []:
        cabeceras[(h.get("name") or "").lower()] = h.get("value") or ""

    de = decodificar(cabeceras.get("from", ""))
    nombre, email = parseaddr(de)
    nombre = limpiar(nombre)
    email = (email or "").strip().lower()
    dominio = email.split("@")[-1] if "@" in email else "(desconocido)"
    if not nombre:
        nombre = email.split("@")[0] or "(sin remitente)"

    try:
        fecha = int(m.get("internalDate") or 0)
    except Exception:
        fecha = 0

    etiquetas = m.get("labelIds") or []
    categoria = 5
    for et in etiquetas:
        if et in CATEGORIAS:
            categoria = CATEGORIAS[et]
            break

    return (
        m.get("id"),
        m.get("threadId"),
        fecha,
        limpiar(decodificar(cabeceras.get("subject", "")))[:140],
        nombre[:90],
        email[:120],
        dominio[:90],
        ",".join(etiquetas),
        int(m.get("sizeEstimate") or 0),
        categoria,
        1 if "UNREAD" in etiquetas else 0,
        1 if cabeceras.get("list-unsubscribe") else 0,
    )


def categoria_de(etiquetas):
    for et in etiquetas:
        if et in CATEGORIAS:
            return CATEGORIAS[et]
    return 5


def main():
    ap = argparse.ArgumentParser(description="Sincroniza la cache con Gmail.")
    ap.add_argument("--simular", action="store_true", help="solo cuenta, no cambia nada")
    args = ap.parse_args()

    os.chdir(BASE)
    conn = sqlite3.connect(RUTA_DB)
    conn.execute("PRAGMA journal_mode=WAL")

    en_cache = {r[0] for r in conn.execute("SELECT id FROM mensajes")}
    log("Cache local: %s correos." % miles(len(en_cache)))
    if not en_cache:
        log("La cache esta vacia. Ejecuta primero: python analizar_gmail.py")
        return

    svc = autenticar()
    actuales = listar_actuales(svc)

    nuevos = [i for i in actuales if i not in en_cache]
    borrados = [i for i in en_cache if i not in actuales]
    comunes = len(actuales) - len(nuevos)

    log("")
    log("  ya estaban y siguen      : %s" % miles(comunes))
    log("  llegaron despues         : %s" % miles(len(nuevos)))
    log("  ya no existen (papelera) : %s" % miles(len(borrados)))
    log("")

    if args.simular:
        log("Simulacion. Nada se modifico.")
        return

    # ---- 1. etiquetas, categoria y leido/no leido de los que ya estaban ----
    log("Actualizando etiquetas y estado de lectura...")
    # una tabla temporal y un solo UPDATE, en vez de 22.000 UPDATE sueltos
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS tmp_labels (id TEXT PRIMARY KEY, etiquetas TEXT, categoria INTEGER, noleido INTEGER)")
    conn.execute("DELETE FROM tmp_labels")
    conn.executemany(
        "INSERT OR REPLACE INTO tmp_labels VALUES (?,?,?,?)",
        [(mid, ",".join(et), categoria_de(et), 1 if "UNREAD" in et else 0)
         for mid, et in actuales.items()],
    )
    conn.execute(
        """UPDATE mensajes SET
               etiquetas = (SELECT etiquetas FROM tmp_labels t WHERE t.id = mensajes.id),
               categoria = (SELECT categoria FROM tmp_labels t WHERE t.id = mensajes.id),
               noleido   = (SELECT noleido   FROM tmp_labels t WHERE t.id = mensajes.id)
           WHERE id IN (SELECT id FROM tmp_labels)"""
    )
    conn.commit()
    log("  %s correos actualizados." % miles(comunes))

    # ---- 2. borrar los que ya no existen ----
    if borrados:
        log("Quitando de la cache los que ya no existen...")
        for i in range(0, len(borrados), 900):
            trozo = borrados[i:i + 900]
            conn.execute(
                "DELETE FROM mensajes WHERE id IN (%s)" % ",".join("?" * len(trozo)),
                trozo,
            )
        conn.commit()
        log("  %s correos fuera." % miles(len(borrados)))

    # ---- 3. descargar los nuevos ----
    if nuevos:
        log("Descargando los %s correos nuevos..." % miles(len(nuevos)))
        LOTE = 40
        hechos = 0
        for i in range(0, len(nuevos), LOTE):
            trozo = nuevos[i:i + LOTE]
            resultados = []
            errores = []

            def guardar(_rid, respuesta, error):
                if error is not None:
                    errores.append(_rid)
                elif respuesta:
                    resultados.append(respuesta)

            lote = svc.new_batch_http_request(callback=guardar)
            for mid in trozo:
                lote.add(svc.users().messages().get(
                    userId="me", id=mid, format="metadata",
                    metadataHeaders=CABECERAS, fields=CAMPOS))
            try:
                lote.execute()
            except Exception:
                resultados = []
                for mid in trozo:
                    try:
                        resultados.append(svc.users().messages().get(
                            userId="me", id=mid, format="metadata",
                            metadataHeaders=CABECERAS, fields=CAMPOS).execute())
                    except Exception:
                        errores.append(mid)

            filas = [fila_desde_respuesta(r) for r in resultados]
            if filas:
                conn.executemany(
                    "INSERT OR REPLACE INTO mensajes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    filas,
                )
                conn.commit()
            hechos += len(filas)
            if hechos % 200 == 0 or i + LOTE >= len(nuevos):
                log("  %s / %s" % (miles(hechos), miles(len(nuevos))))
        if errores:
            log("  %s no se pudieron leer; vuelve a ejecutar." % miles(len(errores)))

    # ---- 4. catalogo de etiquetas ----
    lista = svc.users().labels().list(userId="me").execute().get("labels") or []
    conn.execute("DELETE FROM etiquetas")
    conn.executemany(
        "INSERT OR REPLACE INTO etiquetas VALUES (?,?,?)",
        [(l["id"], l.get("name", ""), l.get("type", "")) for l in lista],
    )
    conn.commit()
    log("Catalogo de etiquetas: %d." % len(lista))

    total = conn.execute("SELECT COUNT(*) FROM mensajes").fetchone()[0]
    log("")
    log("Cache sincronizada: %s correos." % miles(total))
    conn.close()

    # ---- 5. regenerar dashboard y reporte ----
    log("")
    log("Regenerando datos del dashboard...")
    import analizar_gmail
    analizar_gmail.RUTA_DB = RUTA_DB
    conn2 = analizar_gmail.abrir_db()
    analizar_gmail.generar_salidas(conn2)
    conn2.close()

    log("")
    log("Listo. Abre dashboard.html")


if __name__ == "__main__":
    sys.exit(main())
