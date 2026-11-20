# -*- coding: utf-8 -*-
"""
analizar_gmail.py
=================
Descarga los METADATOS de tu Gmail (remitente, asunto, fecha, etiquetas, tamano)
usando la API oficial de Gmail con OAuth, y genera los datos del dashboard.

No descarga el cuerpo de los correos: el permiso solicitado es solo
gmail.metadata (lectura de cabeceras y etiquetas).

Uso:
    python analizar_gmail.py                # descarga + genera dashboard
    python analizar_gmail.py --resumen      # solo regenera el dashboard desde la cache
    python analizar_gmail.py --tope 500     # prueba con 500 correos
    python analizar_gmail.py --reiniciar    # borra la cache y empieza de cero

Salidas:
    datos_gmail.js        -> datos que consume dashboard.html
    reporte_limpieza.md   -> informe con consultas listas para Gmail
"""

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_CREDS = os.path.join(BASE, "client_secret.json")
RUTA_TOKEN = os.path.join(BASE, "token.json")
RUTA_DB = os.path.join(BASE, "cache_gmail.db")
RUTA_JS = os.path.join(BASE, "datos_gmail.js")
RUTA_REPORTE = os.path.join(BASE, "reporte_limpieza.md")
RUTA_DASH = os.path.join(BASE, "dashboard.html")

# Permiso minimo: solo metadatos (cabeceras + etiquetas). No lee el cuerpo.
SCOPES = ["https://www.googleapis.com/auth/gmail.metadata"]

CABECERAS = ["From", "Subject", "Date", "List-Unsubscribe", "Reply-To"]
CAMPOS = "id,threadId,labelIds,internalDate,sizeEstimate,payload/headers"

# El endpoint de lotes de Gmail falla seguido con 502. Si falla una vez,
# se apaga para el resto de la ejecucion y se pide uno por uno.
USAR_LOTES = True

# Etiquetas de sistema que no aportan nada al analisis
ETIQUETAS_IGNORADAS = {
    "INBOX", "UNREAD", "SENT", "DRAFT", "TRASH", "SPAM", "CHAT",
    "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS",
    "CATEGORY_UPDATES", "CATEGORY_FORUMS",
    "IMPORTANT", "YELLOW_STAR",  # las pone Gmail solo: tapan a las etiquetas propias
}

CATEGORIAS = {
    "CATEGORY_PERSONAL": 0,
    "CATEGORY_SOCIAL": 1,
    "CATEGORY_PROMOTIONS": 2,
    "CATEGORY_UPDATES": 3,
    "CATEGORY_FORUMS": 4,
}
NOMBRE_CATEGORIA = {
    0: "Personal", 1: "Social", 2: "Promociones",
    3: "Actualizaciones", 4: "Foros", 5: "Otros",
}

DIA_MS = 86400000


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def log(msg=""):
    print(msg, flush=True)


def decodificar(valor):
    """Decodifica cabeceras con acentos (=?UTF-8?...?=)."""
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


def limpiar_espacios(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def abrir_db():
    conn = sqlite3.connect(RUTA_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS mensajes (
            id TEXT PRIMARY KEY,
            hilo TEXT,
            fecha INTEGER,
            asunto TEXT,
            nombre TEXT,
            email TEXT,
            dominio TEXT,
            etiquetas TEXT,
            peso INTEGER,
            categoria INTEGER,
            noleido INTEGER,
            boletin INTEGER
        )"""
    )
    conn.execute("CREATE TABLE IF NOT EXISTS etiquetas (id TEXT PRIMARY KEY, nombre TEXT, tipo TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS estado (clave TEXT PRIMARY KEY, valor TEXT)")
    conn.commit()
    return conn


# --------------------------------------------------------------------------- #
# Autenticacion
# --------------------------------------------------------------------------- #
def instrucciones_credenciales():
    log("")
    log("=" * 74)
    log("  FALTA EL ARCHIVO  client_secret.json")
    log("=" * 74)
    log("")
    log("  Hay que crear las credenciales de Google (una sola vez, ~5 minutos):")
    log("")
    log("  1. Abre  https://console.cloud.google.com/projectcreate")
    log("     y crea un proyecto, por ejemplo:  Dashboard Gmail")
    log("")
    log("  2. Ve a  https://console.cloud.google.com/apis/library/gmail.googleapis.com")
    log("     y pulsa  HABILITAR")
    log("")
    log("  3. Ve a  https://console.cloud.google.com/apis/credentials/consent")
    log("     - Tipo de usuario: Externo  ->  CREAR")
    log("     - Nombre de la app: Dashboard Gmail")
    log("     - Correo de asistencia y de contacto: tu correo")
    log("     - GUARDAR Y CONTINUAR (los pasos de permisos se dejan como estan)")
    log("     - En 'Usuarios de prueba' agregate a ti mismo y guarda")
    log("")
    log("  4. Ve a  https://console.cloud.google.com/apis/credentials")
    log("     - CREAR CREDENCIALES  ->  ID de cliente de OAuth")
    log("     - Tipo de aplicacion:  Aplicacion de escritorio  ->  CREAR")
    log("     - DESCARGA JSON")
    log("")
    log("  5. Renombra el archivo descargado a  client_secret.json")
    log("     y colocalo en esta misma carpeta:")
    log("     " + BASE)
    log("")
    log("  6. Vuelve a ejecutar:  python analizar_gmail.py")
    log("")


def autenticar():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(RUTA_TOKEN):
        try:
            creds = Credentials.from_authorized_user_file(RUTA_TOKEN, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        log("Sesion de Google reutilizada (token.json).")
    else:
        if creds and creds.expired and creds.refresh_token:
            log("Renovando el acceso a Gmail...")
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(RUTA_CREDS):
                instrucciones_credenciales()
                sys.exit(1)
            log("")
            log("Se abrira el navegador para autorizar el acceso a tu Gmail.")
            log("Inicia sesion con la cuenta que quieres analizar y acepta el permiso.")
            log("")
            flujo = InstalledAppFlow.from_client_secrets_file(RUTA_CREDS, SCOPES)
            creds = flujo.run_local_server(port=0, prompt="consent")

        with open(RUTA_TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        log("Acceso guardado en token.json (no lo compartas).")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #
def listar_ids(svc, consulta, tope=None):
    ids = []
    token = None
    log("Listando los correos del buzon...")
    while True:
        peticion = svc.users().messages().list(
            userId="me",
            maxResults=500,
            q=consulta,
            pageToken=token,
            fields="messages/id,nextPageToken",
        )
        respuesta = peticion.execute()
        for m in respuesta.get("messages") or []:
            ids.append(m["id"])
        token = respuesta.get("nextPageToken")
        log("  ... %s correos encontrados" % f"{len(ids):,}".replace(",", "."))
        if not token:
            break
        if tope and len(ids) >= tope:
            break
    if tope:
        ids = ids[:tope]
    return ids


def fila_desde_respuesta(m):
    """Convierte la respuesta de la API en una fila de SQLite."""
    cabeceras = {}
    for h in (m.get("payload") or {}).get("headers") or []:
        cabeceras[(h.get("name") or "").lower()] = h.get("value") or ""

    de = decodificar(cabeceras.get("from", ""))
    nombre, email = parseaddr(de)
    nombre = limpiar_espacios(nombre)
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

    asunto = limpiar_espacios(decodificar(cabeceras.get("subject", "")))[:140]
    boletin = 1 if cabeceras.get("list-unsubscribe") else 0

    return (
        m.get("id"),
        m.get("threadId"),
        fecha,
        asunto,
        nombre[:90],
        email[:120],
        dominio[:90],
        ",".join(etiquetas),
        int(m.get("sizeEstimate") or 0),
        categoria,
        1 if "UNREAD" in etiquetas else 0,
        boletin,
    )


def descargar(conn, svc, ids, pausa, lote_tam=40):
    global USAR_LOTES
    ya = set()
    for (fila,) in conn.execute("SELECT id FROM mensajes"):
        ya.add(fila)

    pendientes = [i for i in ids if i not in ya]
    if not pendientes:
        log("La cache ya tiene los %s correos. Nada que descargar." % f"{len(ya):,}".replace(",", "."))
        return

    total = len(pendientes)
    log("")
    log("Descargando metadatos: %s correos (ya tenias %s en cache)."
        % (f"{total:,}".replace(",", "."), f"{len(ya):,}".replace(",", ".")))
    log("Permiso: solo cabeceras y etiquetas. No se lee el contenido.")
    log("")

    LOTE = lote_tam  # cada lectura cuesta 5 unidades de cuota (limite: 250 por segundo)
    inicio = time.time()
    total_ids = len(ids)
    pausa_actual = pausa
    ronda = 0

    while pendientes and ronda < 5:
        ronda += 1
        if ronda > 1:
            espera = 15 * (ronda - 1)
            log("")
            log("  Reintento %d: quedan %s correos. Esperando %d s para que Google libere cuota..."
                % (ronda - 1, f"{len(pendientes):,}".replace(",", "."), espera))
            time.sleep(espera)

        fallidos = []
        cola = list(pendientes)
        pendientes = []

        while cola:
            trozo = cola[:LOTE]
            resultados = []
            errores = []

            def guardar(_rid, respuesta, error):
                if error is not None:
                    errores.append(_rid)
                    return
                if respuesta:
                    resultados.append(respuesta)

            if USAR_LOTES:
                lote = svc.new_batch_http_request(callback=guardar)
                for mid in trozo:
                    lote.add(
                        svc.users().messages().get(
                            userId="me", id=mid, format="metadata",
                            metadataHeaders=CABECERAS, fields=CAMPOS,
                        )
                    )
                try:
                    lote.execute()
                except Exception as e:
                    # El endpoint de lotes devuelve 502 con frecuencia. Se
                    # desactiva para el resto de la ejecucion y se sigue
                    # pidiendo uno por uno, que si funciona.
                    corto = str(e).splitlines()[0][:80]
                    log("  aviso: lotes no disponibles (%s). Sigo individual." % corto)
                    USAR_LOTES = False

            if not USAR_LOTES:
                resultados = []
                errores = []
                for mid in trozo:
                    for intento in range(3):
                        try:
                            resp = svc.users().messages().get(
                                userId="me", id=mid, format="metadata",
                                metadataHeaders=CABECERAS, fields=CAMPOS,
                            ).execute()
                            resultados.append(resp)
                            break
                        except Exception:
                            if intento == 2:
                                errores.append(mid)
                            else:
                                time.sleep(1.2 * (intento + 1))

            filas = [fila_desde_respuesta(resp) for resp in resultados]
            if filas:
                conn.executemany("INSERT OR REPLACE INTO mensajes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", filas)
                conn.commit()

            fallidos.extend(errores)
            cola = cola[LOTE:]

            # si falla buena parte del lote, es cuota: bajar el ritmo
            if len(errores) > len(trozo) * 0.4:
                pausa_actual = min(pausa_actual * 1.7, 8.0)

            en_db = conn.execute("SELECT COUNT(*) FROM mensajes").fetchone()[0]
            transcurrido = time.time() - inicio
            ritmo = en_db / transcurrido if transcurrido > 0 else 0
            restante = (total_ids - en_db) / ritmo if ritmo > 0 else 0
            pct = en_db * 100.0 / total_ids if total_ids else 100
            barra = "=" * int(pct / 3.4)
            log("  [%-28s] %5.1f%%  %s / %s   faltan %s min"
                % (barra, pct, f"{en_db:,}".replace(",", "."),
                   f"{total_ids:,}".replace(",", "."), int(restante / 60)))

            time.sleep(pausa_actual)

        pendientes = fallidos
        if pendientes:
            log("")
            log("  Quedaron %s correos sin descargar en esta pasada."
                % f"{len(pendientes):,}".replace(",", "."))

    if pendientes:
        log("")
        log("  %s correos siguen sin descargarse. Ejecuta el script otra vez"
            " (retoma solo esos)." % f"{len(pendientes):,}".replace(",", "."))
    else:
        log("")
        log("  Todos los correos del buzon estan descargados.")
    log("")
    log("Descarga completada en %.1f minutos." % ((time.time() - inicio) / 60))


# --------------------------------------------------------------------------- #
# Analisis y generacion de datos
# --------------------------------------------------------------------------- #
def generar_salidas(conn):
    log("")
    log("Analizando %s correos..." % f"{conn.execute('SELECT COUNT(*) FROM mensajes').fetchone()[0]:,}".replace(",", "."))

    filas = list(conn.execute(
        """SELECT id, fecha, asunto, nombre, email, dominio, etiquetas, peso,
                  categoria, noleido, boletin
           FROM mensajes ORDER BY fecha ASC"""
    ))

    etiquetas_catalogo = {}
    for lid, nombre, tipo in conn.execute("SELECT id, nombre, tipo FROM etiquetas"):
        etiquetas_catalogo[lid] = (nombre, tipo)

    if not filas:
        log("No hay correos en la cache. Ejecuta primero la descarga.")
        return

    # ---- remitentes -------------------------------------------------------
    contador = Counter(f[4] for f in filas)
    orden = [e for e, _ in contador.most_common()]
    indice = {e: i for i, e in enumerate(orden)}
    info = {}
    for f in filas:
        if f[4] not in info:
            info[f[4]] = (f[3], f[4], f[5])

    remitentes = []
    for e in orden:
        nombre, correo, dominio = info[e]
        remitentes.append([nombre, correo, dominio])

    # ---- etiquetas: se guardan como mascara de bits (max 30) --------------
    uso = Counter()
    for f in filas:
        for et in f[6].split(","):
            if et and et not in ETIQUETAS_IGNORADAS:
                uso[et] += 1
    elegidas = [e for e, _ in uso.most_common(30)]
    posicion = {e: i for i, e in enumerate(elegidas)}
    etiquetas = []
    for et in elegidas:
        nombre, tipo = etiquetas_catalogo.get(et, (et.replace("Label_", "Etiqueta "), "user"))
        etiquetas.append({"id": et, "n": nombre, "tipo": tipo})

    # ---- columnas --------------------------------------------------------
    col = {"f": [], "h": [], "p": [], "r": [], "c": [], "u": [], "a": [], "b": [], "e": [], "s": []}
    peso_total = 0
    no_leidos = 0
    boletines = 0
    for f in filas:
        fecha = f[1] or 0
        peso = f[7] or 0
        peso_total += peso
        no_leidos += f[9]
        boletines += f[10]
        col["f"].append(fecha // DIA_MS if fecha else 0)
        col["h"].append((fecha // 3600000) % 24 if fecha else 0)
        col["p"].append(peso)
        col["r"].append(indice[f[4]])
        col["c"].append(f[8])
        col["u"].append(f[9])
        col["a"].append(1 if peso >= 1000000 else 0)
        col["b"].append(f[10])
        mascara = 0
        for et in f[6].split(","):
            if et in posicion:
                mascara |= (1 << posicion[et])
        col["e"].append(mascara)
        col["s"].append(f[2][:140])

    fechas_validas = [x for x in col["f"] if x > 0]
    desde = min(fechas_validas) * DIA_MS
    hasta = max(fechas_validas) * DIA_MS

    datos = {
        "generado": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "cuenta": (conn.execute("SELECT valor FROM estado WHERE clave='cuenta'").fetchone() or [""])[0],
        "total": len(filas),
        "peso": peso_total,
        "noLeidos": no_leidos,
        "conAdjunto": sum(col["a"]),
        "boletines": boletines,
        "desde": desde,
        "hasta": hasta,
        "remitentes": remitentes,
        "etiquetas": etiquetas,
        "c": col,
    }

    with open(RUTA_JS, "w", encoding="utf-8") as f:
        f.write("window.DATOS_GMAIL = ")
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    log("Datos del dashboard: %s (%.1f MB)" % (os.path.basename(RUTA_JS), os.path.getsize(RUTA_JS) / 1048576.0))

    escribir_reporte(filas, remitentes, datos)


def mb(bytes_):
    return bytes_ / 1048576.0


def fmt_mb(b):
    v = mb(b)
    if v >= 1024:
        return ("%.2f GB" % (v / 1024)).replace(".", ",")
    return (("%.0f MB" % v) if v >= 10 else ("%.1f MB" % v)).replace(".", ",")


def escribir_reporte(filas, remitentes, datos):
    hoy = dt.datetime.now()
    anio_actual = hoy.year
    total = len(filas)
    peso_total = datos["peso"]

    por_remitente = defaultdict(lambda: {"n": 0, "peso": 0, "noleido": 0, "viejo": 0})
    for f in filas:
        d = por_remitente[f[4]]
        d["n"] += 1
        d["peso"] += f[7] or 0
        d["noleido"] += f[9]
        if f[1] and (hoy - dt.datetime.utcfromtimestamp(f[1] / 1000.0)).days > 365 * 5:
            d["viejo"] += 1

    ranking = sorted(por_remitente.items(), key=lambda kv: kv[1]["n"], reverse=True)

    def consulta_para(correo):
        return "from:%s" % correo

    lineas = []
    add = lineas.append
    add("# Reporte de limpieza de Gmail")
    add("")
    add("Generado el %s sobre **%s correos** (%s en total)." % (hoy.strftime("%d/%m/%Y %H:%M"), f"{total:,}".replace(",", "."), fmt_mb(peso_total)))
    add("")
    add("Rango del buzón: %s a %s." % (
        dt.datetime.utcfromtimestamp(datos["desde"] / 1000.0).strftime("%d/%m/%Y"),
        dt.datetime.utcfromtimestamp(datos["hasta"] / 1000.0).strftime("%d/%m/%Y")))
    add("")
    add("## Radiografía")
    add("")
    add("| Indicador | Valor |")
    add("|---|---|")
    add("| Correos totales | %s |" % f"{total:,}".replace(",", "."))
    add("| Espacio ocupado | %s |" % fmt_mb(peso_total))
    add("| Correos sin leer | %s (%.1f%%) |" % (f"{datos['noLeidos']:,}".replace(",", "."), datos["noLeidos"] * 100.0 / total))
    add("| Remitentes distintos | %s |" % f"{len(remitentes):,}".replace(",", "."))
    add("| Correos de más de 1 MB | %s |" % f"{datos['conAdjunto']:,}".replace(",", "."))
    add("| Boletines detectados | %s |" % f"{datos['boletines']:,}".replace(",", "."))
    add("")
    add("## Reglas de limpieza sugeridas")
    add("")
    add("Copia la consulta y pégala en el buscador de Gmail. Revisa el resultado")
    add("antes de borrar: el número que aparece al lado es lo que encontrará hoy.")
    add("")

    reglas = []

    promos_viejas = [f for f in filas if f[8] == 2 and f[1] and (hoy - dt.datetime.utcfromtimestamp(f[1] / 1000.0)).days > 365 * 3]
    reglas.append(("Promociones de hace más de 3 años",
                   "category:promotions older_than:3y", promos_viejas,
                   "Suelen ser ofertas caducadas. Es la limpieza con mejor relación esfuerzo/beneficio."))

    noleidos_viejos = [f for f in filas if f[9] == 1 and f[1] and (hoy - dt.datetime.utcfromtimestamp(f[1] / 1000.0)).days > 365 * 2]
    reglas.append(("Sin leer desde hace más de 2 años",
                   "is:unread older_than:2y", noleidos_viejos,
                   "Si no lo abriste en dos años, no lo vas a abrir."))

    pesados = [f for f in filas if (f[7] or 0) >= 5 * 1024 * 1024 and f[1] and (hoy - dt.datetime.utcfromtimestamp(f[1] / 1000.0)).days > 365 * 2]
    reglas.append(("Adjuntos pesados (más de 5 MB) con más de 2 años",
                   "larger:5M older_than:2y", pesados,
                   "Aquí está la mayor parte del espacio. Los archivos importantes suelen estar descargados."))

    boletines_viejos = [f for f in filas if f[10] == 1 and f[1] and (hoy - dt.datetime.utcfromtimestamp(f[1] / 1000.0)).days > 365 * 5]
    reglas.append(("Boletines de hace más de 5 años",
                   "older_than:5y (category:promotions OR category:updates)", boletines_viejos,
                   "Newsletters antiguas: información que ya caducó."))

    for titulo, consulta, conjunto, motivo in reglas:
        add("### %s" % titulo)
        add("")
        add("- Correos: **%s**  |  Espacio: **%s**" % (f"{len(conjunto):,}".replace(",", "."), fmt_mb(sum(f[7] or 0 for f in conjunto))))
        add("- Por que: %s" % motivo)
        add("")
        add("```")
        add(consulta)
        add("```")
        add("")
        add("Buscar en Gmail: https://mail.google.com/mail/u/0/#search/" + consulta.replace(" ", "+").replace("(", "%28").replace(")", "%29"))
        add("")

    add("### Remitentes con más volumen y cero interés")
    add("")
    add("| Remitente | Correos | Espacio | Sin leer | Consulta |")
    add("|---|---|---|---|---|")
    candidatos = 0
    for correo, d in ranking[:60]:
        if d["noleido"] == d["n"] and d["n"] >= 50:
            nombre = next((r[0] for r in remitentes if r[1] == correo), correo)
            add("| %s | %s | %s | 100%% | `%s` |" % (nombre[:40], d["n"], fmt_mb(d["peso"]), consulta_para(correo)))
            candidatos += 1
    if candidatos == 0:
        add("| (ninguno cumple el criterio) | | | | |")
    add("")
    add("### Los 25 remitentes que más correo te mandan")
    add("")
    add("| # | Remitente | Correos | % del buzón | Espacio | Sin leer |")
    add("|---|---|---|---|---|---|")
    for i, (correo, d) in enumerate(ranking[:25], 1):
        nombre = next((r[0] for r in remitentes if r[1] == correo), correo)
        add("| %d | %s | %s | %.1f%% | %s | %d |" % (
            i, nombre[:45], d["n"], d["n"] * 100.0 / total, fmt_mb(d["peso"]), d["noleido"]))
    add("")
    add("---")
    add("")
    add("Este informe es orientativo: los tamaños son la estimación de Gmail y")
    add("las categorías dependen de cómo Gmail clasificó cada correo hace años.")

    with open(RUTA_REPORTE, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    log("Reporte: %s" % os.path.basename(RUTA_REPORTE))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Analiza tu Gmail y prepara el dashboard.")
    ap.add_argument("--resumen", action="store_true", help="solo regenera datos desde la cache")
    ap.add_argument("--tope", type=int, default=0, help="procesar solo los primeros N correos")
    ap.add_argument("--reiniciar", action="store_true", help="borrar la cache local")
    ap.add_argument("--spam", action="store_true", help="incluir spam y papelera")
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos entre lotes (cuota)")
    ap.add_argument("--lote", type=int, default=40, help="correos por lote (max 100); mas = mas rapido")
    ap.add_argument("--no-abrir", action="store_true", help="no abrir el dashboard al terminar")
    args = ap.parse_args()

    os.chdir(BASE)

    if args.reiniciar and os.path.exists(RUTA_DB):
        for sufijo in ("", "-wal", "-shm"):
            try:
                os.remove(RUTA_DB + sufijo)
            except OSError:
                pass
        log("Cache borrada.")

    conn = abrir_db()

    if not args.resumen:
        svc = autenticar()

        try:
            perfil = svc.users().getProfile(userId="me").execute()
            log("Cuenta: %s" % perfil.get("emailAddress"))
            if perfil.get("emailAddress"):
                conn.execute("INSERT OR REPLACE INTO estado VALUES ('cuenta', ?)",
                             (perfil["emailAddress"],))
                conn.commit()
        except Exception:
            perfil = {}

        try:
            lista = svc.users().labels().list(userId="me").execute().get("labels") or []
            conn.executemany(
                "INSERT OR REPLACE INTO etiquetas VALUES (?,?,?)",
                [(l["id"], l.get("name", ""), l.get("type", "")) for l in lista],
            )
            conn.commit()
            log("Etiquetas encontradas: %d" % len(lista))
        except Exception as e:
            log("Aviso: no se pudieron leer las etiquetas (%s)" % e)

        consulta = "in:anywhere" if args.spam else None
        ids = listar_ids(svc, consulta, args.tope or None)
        descargar(conn, svc, ids, args.pausa, max(1, min(100, args.lote)))

    generar_salidas(conn)
    conn.close()

    log("")
    log("=" * 74)
    log("  LISTO. Abre el dashboard:")
    log("  " + RUTA_DASH)
    log("=" * 74)

    if not args.no_abrir and os.path.exists(RUTA_DASH):
        try:
            os.startfile(RUTA_DASH)
        except Exception:
            pass


if __name__ == "__main__":
    main()
