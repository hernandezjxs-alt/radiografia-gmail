# -*- coding: utf-8 -*-
"""
Crea reglas (filtros) en Gmail desde la linea de comandos.

Necesita un permiso distinto al del dashboard: gmail.settings.basic.
La primera vez abre el navegador para autorizarlo. El token queda en
token_reglas.json y NO toca el del dashboard (que sigue siendo de solo lectura).

Ejemplos:
    python crear_regla.py --listar
    python crear_regla.py --etiqueta Empleo --desde jobalerts-noreply@linkedin.com --saltar-bandeja
    python crear_regla.py --etiqueta Empleo --desde alert@indeed.com --saltar-bandeja --marcar-leido
    python crear_regla.py --desde antiguo@ejemplo.com --borrar
    python crear_regla.py --eliminar ID_DEL_FILTRO

Las reglas de Gmail solo afectan al correo NUEVO. Para limpiar lo que ya
tienes, usa la casilla "Aplicar tambien a las conversaciones que coincidan"
al crear la regla desde la web de Gmail.
"""
import argparse
import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_CREDS = os.path.join(BASE, "client_secret.json")
RUTA_TOKEN = os.path.join(BASE, "token_reglas.json")

SCOPES = ["https://www.googleapis.com/auth/gmail.settings.basic"]


def log(t=""):
    print(t, flush=True)


def autenticar():
    creds = None
    if os.path.exists(RUTA_TOKEN):
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
            log("Falta client_secret.json en esta carpeta.")
            sys.exit(1)
        log("")
        log("Se va a abrir el navegador para autorizar la gestion de reglas.")
        log("Elige tu cuenta y acepta. Es un permiso distinto al del dashboard.")
        log("")
        flujo = InstalledAppFlow.from_client_secrets_file(RUTA_CREDS, SCOPES)
        creds = flujo.run_local_server(port=0)

    with open(RUTA_TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# --------------------------------------------------------------------------- #
# Etiquetas
# --------------------------------------------------------------------------- #
def buscar_etiqueta(svc, nombre):
    lista = svc.users().labels().list(userId="me").execute().get("labels") or []
    for l in lista:
        if l.get("name", "").lower() == nombre.lower():
            return l["id"]
    return None


def asegurar_etiqueta(svc, nombre):
    """Devuelve el id de la etiqueta, creandola si no existe."""
    lid = buscar_etiqueta(svc, nombre)
    if lid:
        return lid, False
    creada = svc.users().labels().create(
        userId="me",
        body={
            "name": nombre,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()
    return creada["id"], True


# --------------------------------------------------------------------------- #
# Filtros
# --------------------------------------------------------------------------- #
ACCIONES = {
    "saltar_bandeja": "INBOX",
    "marcar_leido": "UNREAD",
    "destacar": "IMPORTANT",
    "estrella": "STARRED",
}


def describir(filtro):
    c = filtro.get("criteria", {})
    a = filtro.get("action", {})
    trozos = []
    if c.get("from"):
        trozos.append("de: %s" % c["from"])
    if c.get("to"):
        trozos.append("para: %s" % c["to"])
    if c.get("subject"):
        trozos.append("asunto: %s" % c["subject"])
    if c.get("query"):
        trozos.append("busqueda: %s" % c["query"])
    hechos = []
    if a.get("addLabelIds"):
        hechos.append("etiqueta/accion: %s" % ", ".join(a["addLabelIds"]))
    if a.get("removeLabelIds"):
        hechos.append("quita: %s" % ", ".join(a["removeLabelIds"]))
    return " | ".join(trozos + hechos)


def listar(svc):
    filtros = svc.users().settings().filters().list(userId="me").execute().get("filter") or []
    if not filtros:
        log("No tienes ninguna regla creada.")
        return
    log("Tienes %d regla(s):" % len(filtros))
    log("")
    for f in filtros:
        log("  [%s]" % f.get("id"))
        log("     %s" % describir(f))
    log("")


def main():
    ap = argparse.ArgumentParser(description="Crea reglas (filtros) en Gmail.")
    ap.add_argument("--listar", action="store_true", help="muestra las reglas actuales")
    ap.add_argument("--desde", help="direccion o dominio del remitente (una sola por regla)")
    ap.add_argument("--asunto", help="texto que debe aparecer en el asunto")
    ap.add_argument("--consulta", help="busqueda libre, como en el buscador de Gmail")
    ap.add_argument("--etiqueta", help="nombre de la etiqueta a aplicar (se crea si no existe)")
    ap.add_argument("--saltar-bandeja", action="store_true", help="archiva: no aparece en la bandeja")
    ap.add_argument("--marcar-leido", action="store_true", help="lo marca como leido")
    ap.add_argument("--borrar", action="store_true", help="lo manda a la papelera")
    ap.add_argument("--eliminar", metavar="ID", help="borra una regla por su id")
    ap.add_argument("--si", action="store_true", help="no pide confirmacion")
    args = ap.parse_args()

    svc = autenticar()

    if args.listar:
        listar(svc)
        return

    if args.eliminar:
        svc.users().settings().filters().delete(userId="me", id=args.eliminar).execute()
        log("Regla %s eliminada." % args.eliminar)
        return

    if not (args.desde or args.asunto or args.consulta):
        log("Necesito al menos --desde, --asunto o --consulta.")
        log("Ejemplo: python crear_regla.py --desde alert@indeed.com --saltar-bandeja --etiqueta Empleo")
        sys.exit(1)

    criterios = {}
    if args.desde:
        criterios["from"] = args.desde
    if args.asunto:
        criterios["subject"] = args.asunto
    if args.consulta:
        criterios["query"] = args.consulta

    accion = {"addLabelIds": [], "removeLabelIds": []}

    if args.etiqueta:
        lid, creada = asegurar_etiqueta(svc, args.etiqueta)
        accion["addLabelIds"].append(lid)
        log("Etiqueta '%s' %s." % (args.etiqueta, "creada" if creada else "ya existia"))

    if args.saltar_bandeja:
        accion["removeLabelIds"].append("INBOX")
    if args.marcar_leido:
        accion["removeLabelIds"].append("UNREAD")
    if args.borrar:
        accion["addLabelIds"].append("TRASH")

    if not accion["addLabelIds"] and not accion["removeLabelIds"]:
        log("No indicaste ninguna accion (--saltar-bandeja, --marcar-leido, --borrar o --etiqueta).")
        sys.exit(1)

    log("")
    log("Regla a crear:")
    log("  cuando: %s" % describir({"criteria": criterios, "action": {}}).replace(" | ", " y "))
    log("  hacer:  %s" % (", ".join(filter(None, [
        "etiquetar" if args.etiqueta else "",
        "archivar" if args.saltar_bandeja else "",
        "marcar leido" if args.marcar_leido else "",
        "MANDAR A PAPELERA" if args.borrar else "",
    ]))))
    log("")

    if args.borrar and not args.si:
        log("OJO: esta regla manda correo a la papelera automaticamente.")
        log("Se puede recuperar 30 dias, pero es mejor probarla primero archivando.")
        log("Si de verdad quieres borrar, agrega --si")
        sys.exit(2)

    if not args.si:
        r = input("Crear la regla? (s/n): ").strip().lower()
        if r not in ("s", "si", "sí", "y"):
            log("Cancelado.")
            return

    try:
        creada = svc.users().settings().filters().create(
            userId="me", body={"criteria": criterios, "action": accion}
        ).execute()
        log("")
        log("Regla creada con id %s." % creada.get("id"))
        log("Solo afecta al correo NUEVO. Para el que ya tienes, usa la web de Gmail")
        log("y marca 'Aplicar tambien a las conversaciones que coincidan'.")
    except HttpError as e:
        log("No se pudo crear: %s" % e)
        log("Si dice 'insufficientPermissions', borra token_reglas.json y vuelve a ejecutar.")


if __name__ == "__main__":
    main()
