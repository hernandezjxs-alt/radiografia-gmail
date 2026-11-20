# -*- coding: utf-8 -*-
"""
Crea una etiqueta (carpeta) por remitente y mueve ahi todos sus correos.

Necesita el permiso gmail.modify: lectura y escritura sobre el correo.
Solo hace dos cosas: crear etiquetas y quitar el correo de la bandeja
(no borra nada, todo queda en su etiqueta).

Uso:
    python organizar_correos.py --local     # cuenta desde la cache, sin conectarse
    python organizar_correos.py --simular   # consulta Gmail y muestra que haria
    python organizar_correos.py --aplicar   # lo hace de verdad

La lista de remitentes y nombres de carpeta esta en etiquetas.json.
"""
import argparse
import json
import os
import sqlite3
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_CREDS = os.path.join(BASE, "client_secret.json")
RUTA_TOKEN = os.path.join(BASE, "token_organizar.json")
RUTA_CONFIG = os.path.join(BASE, "etiquetas.json")
RUTA_DB = os.path.join(BASE, "cache_gmail.db")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",          # etiquetar y mover
    "https://www.googleapis.com/auth/gmail.settings.basic",  # crear reglas
]

# nombre de la carpeta  ->  direccion del remitente
POR_DEFECTO = [
    ["LinkedIn Empleo", "jobalerts-noreply@linkedin.com"],
    ["LinkedIn Newsletter", "newsletters-noreply@linkedin.com"],
    ["LinkedIn Avisos", "updates-noreply@linkedin.com"],
    ["Portales de empleo", "computrabajo.com"],
    ["Portales de empleo", "trabajando.com"],
    ["Portales de empleo", "indeed.com"],
    ["Portales de empleo", "indeedemail.com"],
    ["Portales de empleo", "laborum.cl"],
    ["Portales de empleo", "laborum.com"],
    ["Geovictoria", "no-reply@geovictoria.com"],
    ["IDAcademy", "team@idacademy.co"],
    ["IDAcademy", "team@idacademy.es"],
    ["IKEA", "noreply@news.email.ikea.cl"],
    ["Tenpo", "paratodos@tenpo.cl"],
    ["Banco Santander", "banco@mensajeria.santander.cl"],
    ["Banco Santander", "mensajeria@santander.cl"],
    ["GitHub", "github.com"],
]


def log(t=""):
    print(t, flush=True)


def cargar_mapa():
    """Lee etiquetas.json, o lo crea con la lista por defecto."""
    if os.path.exists(RUTA_CONFIG):
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            datos = json.load(f)
        return [[d["carpeta"], d["remitente"]] for d in datos]

    with open(RUTA_CONFIG, "w", encoding="utf-8") as f:
        json.dump([{"carpeta": c, "remitente": r} for c, r in POR_DEFECTO],
                  f, ensure_ascii=False, indent=2)
    log("Cree etiquetas.json con %d remitentes. Editalo si quieres otros nombres."
        % len(POR_DEFECTO))
    return [list(x) for x in POR_DEFECTO]


# --------------------------------------------------------------------------- #
# Conteo local (sin conectarse a Gmail)
# --------------------------------------------------------------------------- #
def contar_local(mapa):
    if not os.path.exists(RUTA_DB):
        log("No hay cache_gmail.db todavia.")
        return
    conn = sqlite3.connect("file:%s?mode=ro" % RUTA_DB.replace("\\", "/"), uri=True)
    log("")
    log("%-22s %8s %10s  %s" % ("CARPETA", "CORREOS", "ESPACIO", "REMITENTE"))
    log("-" * 78)
    total = total_peso = 0
    for carpeta, rem in mapa:
        fila = conn.execute(
            "SELECT COUNT(*), SUM(peso) FROM mensajes WHERE email = ?", (rem,)
        ).fetchone()
        n = fila[0] or 0
        peso = fila[1] or 0
        total += n
        total_peso += peso
        log("%-22s %8s %9.0f MB  %s" % (
            carpeta[:22], "{:,}".format(n).replace(",", "."),
            peso / 1048576.0, rem))
    log("-" * 78)
    log("%-22s %8s %9.0f MB" % ("TOTAL", "{:,}".format(total).replace(",", "."),
                                total_peso / 1048576.0))
    conn.close()


# --------------------------------------------------------------------------- #
# Gmail
# --------------------------------------------------------------------------- #
def scopes_guardados():
    """Los permisos que realmente se aceptaron la ultima vez."""
    if not os.path.exists(RUTA_TOKEN):
        return []
    try:
        with open(RUTA_TOKEN, encoding="utf-8") as f:
            return json.load(f).get("scopes") or []
    except Exception:
        return []


def autenticar():
    creds = None
    # Si al token le falta algun permiso (por ejemplo, el de crear reglas,
    # que se agregó despues), hay que volver a autorizar.
    if set(SCOPES).issubset(set(scopes_guardados())):
        try:
            creds = Credentials.from_authorized_user_file(RUTA_TOKEN, SCOPES)
        except Exception:
            creds = None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not os.path.exists(RUTA_CREDS):
            log("Falta client_secret.json.")
            sys.exit(1)
        log("")
        log("Se abre el navegador para autorizar la organizacion del correo.")
        log("El permiso incluye dos cosas: modificar correos y crear reglas.")
        log("")
        flujo = InstalledAppFlow.from_client_secrets_file(RUTA_CREDS, SCOPES)
        creds = flujo.run_local_server(port=0)
    with open(RUTA_TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def filtros_existentes(svc):
    return svc.users().settings().filters().list(
        userId="me").execute().get("filter") or []


def crear_filtro(svc, remitente, etiqueta_id, ya_hay):
    """Regla: lo que llegue de este remitente se etiqueta y no pasa por la bandeja."""
    for f in ya_hay:
        c = f.get("criteria") or {}
        if (c.get("from") or "").strip().lower() == remitente.strip().lower():
            return f.get("id"), False

    creado = svc.users().settings().filters().create(
        userId="me",
        body={
            "criteria": {"from": remitente},
            "action": {"addLabelIds": [etiqueta_id], "removeLabelIds": ["INBOX"]},
        },
    ).execute()
    return creado.get("id"), True


def id_etiqueta(svc, nombre):
    lista = svc.users().labels().list(userId="me").execute().get("labels") or []
    for l in lista:
        if l.get("name", "").lower() == nombre.lower():
            return l["id"]
    return None


def listar_correos(svc, remitente):
    """Todos los ids de un remitente, paginando de 500 en 500."""
    ids = []
    token = None
    while True:
        r = svc.users().messages().list(
            userId="me", q="from:%s" % remitente,
            maxResults=500, pageToken=token,
        ).execute()
        for m in r.get("messages") or []:
            ids.append(m["id"])
        token = r.get("nextPageToken")
        if not token:
            break
    return ids


def listar_por_etiqueta(svc, nombre, excluir=None):
    """Todos los ids que llevan una etiqueta, paginando de 500 en 500.
    Si se indica `excluir`, deja fuera los que tambien lleven esa otra."""
    q = 'label:"%s"' % nombre
    if excluir:
        q += ' -label:"%s"' % excluir
    ids = []
    token = None
    while True:
        r = svc.users().messages().list(
            userId="me", q=q, maxResults=500, pageToken=token,
        ).execute()
        for m in r.get("messages") or []:
            ids.append(m["id"])
        token = r.get("nextPageToken")
        if not token:
            break
    return ids


def ejecutar_accion(svc, ids, accion, etiqueta_id=None):
    """accion: 'archivar', 'etiquetar', 'papelera' o 'definitivo'."""
    hechos = 0
    for i in range(0, len(ids), 1000):
        trozo = ids[i:i + 1000]

        if accion == "definitivo":
            svc.users().messages().batchDelete(
                userId="me", body={"ids": trozo}).execute()
        else:
            cuerpo = {"ids": trozo}
            sumar = []
            if etiqueta_id:
                sumar.append(etiqueta_id)
            if accion == "papelera":
                sumar.append("TRASH")
            if sumar:
                cuerpo["addLabelIds"] = sumar
            if accion == "archivar":
                cuerpo["removeLabelIds"] = ["INBOX"]
            svc.users().messages().batchModify(userId="me", body=cuerpo).execute()

        hechos += len(trozo)
        log("     %s / %s" % ("{:,}".format(hechos).replace(",", "."),
                              "{:,}".format(len(ids)).replace(",", ".")))
    return hechos


def main():
    ap = argparse.ArgumentParser(description="Crea carpetas por remitente y mueve su correo.")
    ap.add_argument("--local", action="store_true", help="solo cuenta desde la cache")
    ap.add_argument("--simular", action="store_true", help="consulta Gmail y no cambia nada")
    ap.add_argument("--aplicar", action="store_true", help="crea etiquetas y mueve el correo")
    ap.add_argument("--solo-etiquetar", action="store_true",
                    help="etiqueta pero deja el correo en la bandeja")
    ap.add_argument("--borrar", action="store_true",
                    help="manda a la papelera en vez de archivar (recuperable 30 dias)")
    ap.add_argument("--definitivo", action="store_true",
                    help="borra para siempre, sin pasar por la papelera. LIBERA ESPACIO")
    ap.add_argument("--carpeta", metavar="NOMBRE",
                    help="actua sobre etiquetas ya existentes (varias separadas por coma)")
    ap.add_argument("--proteger", metavar="NOMBRE",
                    help="no toca nada que lleve esta otra etiqueta")
    ap.add_argument("--sin-reglas", action="store_true",
                    help="crea las etiquetas pero no las reglas automaticas")
    ap.add_argument("--solo", metavar="CARPETAS",
                    help="trabaja solo con estas carpetas (separadas por coma)")
    ap.add_argument("--si", action="store_true", help="no pide confirmacion")
    args = ap.parse_args()

    mapa = cargar_mapa()

    if args.solo:
        pedidas = [x.strip().lower() for x in args.solo.split(",") if x.strip()]
        mapa = [x for x in mapa if x[0].lower() in pedidas]
        if not mapa:
            log("Ninguna carpeta de etiquetas.json coincide con: %s" % args.solo)
            return

    if args.local:
        contar_local(mapa)
        return

    if not (args.simular or args.aplicar or args.carpeta):
        log("Indica --local, --simular, --aplicar o --carpeta.")
        return

    # ---- modo: borrar el contenido de una o varias etiquetas existentes ----
    if args.carpeta:
        svc = autenticar()
        carpetas = [c.strip() for c in args.carpeta.split(",") if c.strip()]
        accion = "definitivo" if args.definitivo else "papelera"
        proteger = (args.proteger or "").strip() or None

        if proteger and not id_etiqueta(svc, proteger):
            log("La etiqueta a proteger '%s' no existe. Cancelo por seguridad." % proteger)
            return

        log("")
        log("Accion: %s" % ("BORRAR PARA SIEMPRE (sin vuelta atras)"
                            if accion == "definitivo"
                            else "MOVER A LA PAPELERA (recuperable 30 dias)"))
        if proteger:
            log("Se conserva intacto: '%s'" % proteger)
        log("")
        log("%-24s %9s %10s %8s" % ("CARPETA", "EN TOTAL", "PROTEGIDOS", "BORRAR"))
        log("-" * 55)

        plan = []
        total = total_prot = 0
        for nombre in carpetas:
            if not id_etiqueta(svc, nombre):
                log("%-24s   (esa etiqueta no existe)" % nombre[:24])
                continue
            todos = listar_por_etiqueta(svc, nombre)
            fuera = listar_por_etiqueta(svc, nombre, excluir=proteger) if proteger else todos
            prot = len(todos) - len(fuera)
            if fuera:
                plan.append((nombre, fuera))
            total += len(fuera)
            total_prot += prot
            log("%-24s %9s %10s %8s" % (
                nombre[:24],
                "{:,}".format(len(todos)).replace(",", "."),
                "{:,}".format(prot).replace(",", "."),
                "{:,}".format(len(fuera)).replace(",", ".")))
        log("-" * 55)
        log("%-24s %9s %10s %8s" % ("TOTAL", "",
                                    "{:,}".format(total_prot).replace(",", "."),
                                    "{:,}".format(total).replace(",", ".")))

        if args.simular:
            log("")
            log("Simulacion. Nada se modifico.")
            return
        if not total:
            log("")
            log("No hay nada que borrar.")
            return

        if not args.si:
            log("")
            log("Los protegidos NO se tocan. El resto se va a la %s." %
                ("basura definitiva" if accion == "definitivo" else "papelera"))
            r = input("Continuar? (s/n): ").strip().lower()
            if r not in ("s", "si", "sí", "y"):
                log("Cancelado.")
                return

        hechos = 0
        for nombre, ids in plan:
            log("")
            log("%s  (%s)" % (nombre, "{:,}".format(len(ids)).replace(",", ".")))
            hechos += ejecutar_accion(svc, ids, accion)

        log("")
        log("Listo: %s correos %s." % (
            "{:,}".format(hechos).replace(",", "."),
            "borrados para siempre" if accion == "definitivo" else "en la papelera"))
        if proteger:
            log("'%s' quedo intacta, con todos sus correos." % proteger)
        return

    svc = autenticar()
    accion = "archivar"
    if args.borrar:
        accion = "papelera"
    if args.definitivo:
        accion = "definitivo"
    if args.solo_etiquetar:
        accion = "etiquetar"

    if accion == "definitivo" and not args.si:
        log("")
        log("OJO: --definitivo borra para siempre. Se puede liberar espacio,")
        log("pero no hay vuelta atras ni papelera. Si quieres poder")
        log("arrepentirte, usa --borrar (papelera) o nada (archivar).")
        log("Si de verdad quieres, agrega --si")
        sys.exit(2)

    ids_etiqueta = {}

    # ---------------- fase 1: etiquetas y reglas automaticas ----------------
    log("")
    log("FASE 1 · Etiquetas y reglas para el correo que vaya llegando")
    log("")
    if args.simular:
        for carpeta, rem in mapa:
            log("  %-22s se crearia (si falta) y su regla" % carpeta)
    else:
        ya_hay = filtros_existentes(svc)
        for carpeta, rem in mapa:
            lid = id_etiqueta(svc, carpeta)
            if lid:
                log("  [=] %-21s etiqueta ya existia" % carpeta)
            else:
                creada = svc.users().labels().create(
                    userId="me",
                    body={"name": carpeta, "labelListVisibility": "labelShow",
                          "messageListVisibility": "show"},
                ).execute()
                lid = creada["id"]
                log("  [+] %-21s etiqueta creada" % carpeta)
            ids_etiqueta[carpeta] = lid

            if args.sin_reglas:
                continue
            try:
                fid, nueva = crear_filtro(svc, rem, lid, ya_hay)
                log("      regla %-9s %s" % ("creada:" if nueva else "ya existia:", rem))
            except HttpError as e:
                log("      regla FALLIDA para %s: %s" % (rem, str(e)[:110]))

    # ---------------- fase 2: el correo que ya esta en el buzon ----------------
    log("")
    log("FASE 2 · Correo que ya esta en el buzon")
    resumen = []
    total = 0
    for carpeta, rem in mapa:
        log("")
        log("%s  <-  %s" % (carpeta, rem))
        ids = listar_correos(svc, rem)
        log("   %s correos" % "{:,}".format(len(ids)).replace(",", "."))
        if not ids:
            resumen.append([carpeta, 0, "sin correos"])
            continue

        if args.simular:
            resumen.append([carpeta, len(ids), "se moveria"])
            total += len(ids)
            continue

        lid = ids_etiqueta.get(carpeta)
        if accion in ("papelera", "definitivo"):
            n = ejecutar_accion(svc, ids, accion)
            estado = "a la papelera" if accion == "papelera" else "BORRADO"
        else:
            n = ejecutar_accion(svc, ids, accion, lid)
            estado = "movido" if accion == "archivar" else "etiquetado"
        resumen.append([carpeta, n, estado])
        total += n

    log("")
    log("=" * 60)
    log("%-22s %8s  %s" % ("CARPETA", "CORREOS", "ESTADO"))
    log("-" * 60)
    for carpeta, n, estado in resumen:
        log("%-22s %8s  %s" % (carpeta[:22], "{:,}".format(n).replace(",", "."), estado))
    log("-" * 60)
    log("%-22s %8s" % ("TOTAL", "{:,}".format(total).replace(",", ".")))
    log("")
    if args.simular:
        log("Simulacion. Nada se modifico. Para hacerlo: --aplicar")
    elif accion == "definitivo":
        log("Borrado permanente terminado. Ese espacio ya esta libre.")
        log("Las reglas siguen activas para el correo que vaya llegando.")
    elif accion == "papelera":
        log("En la papelera. El espacio NO se libera hasta vaciarla.")
        log("Las reglas siguen activas: lo nuevo no volvera a la bandeja.")
    else:
        log("Listo. El correo no se borro: esta en su carpeta, fuera de la bandeja.")
        if not args.sin_reglas:
            log("Las reglas quedan activas: lo que llegue de esos remitentes")
            log("se etiqueta solo y no pasa por la bandeja de entrada.")


if __name__ == "__main__":
    main()
