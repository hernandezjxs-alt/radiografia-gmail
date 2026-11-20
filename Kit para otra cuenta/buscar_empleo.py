# -*- coding: utf-8 -*-
"""
Busca en Gmail los correos de procesos de seleccion reales: ofertas,
entrevistas, pruebas tecnicas, postulaciones y citaciones.

No usa solo las cabeceras: aprovecha el buscador de Gmail, que si indexa
el texto completo de los correos. Y descarta lo que la cache ya sabe que
es boletin o promocion, que es de donde viene casi todo el ruido.

Uso:
    python buscar_empleo.py --listar
    python buscar_empleo.py --listar --csv ofertas.csv
    python buscar_empleo.py --etiquetar "Ofertas y entrevistas" --aplicar

Solo pone la etiqueta. NO archiva ni saca de la bandeja: estos correos
son importantes y conviene tenerlos a la vista.
"""
import argparse
import csv
import os
import sqlite3
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_TOKEN = os.path.join(BASE, "token_organizar.json")
RUTA_DB = os.path.join(BASE, "cache_gmail.db")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

# Portales de empleo, bolsas, boletines y tramites que no son una empresa
# escribiendote por un trabajo.
PORTALES = (
    "linkedin.com OR computrabajo.com OR indeed.com OR trabajando.com OR "
    "trabajos.com OR chiletrabajos.cl OR laborum.cl OR bumeran.com OR "
    "jobrapido.com OR jobrapidoalert.com OR zety.com OR "
    "geovictoria.com OR idacademy.co OR idacademy.es OR buscalibre.com OR "
    "vpitv.com OR mail.bizneo.com OR serviciomigraciones.cl OR minrel.gob.cl OR "
    "arieldiazrios.com"
)

# Correos que hablan del tema pero no son un proceso tuyo.
BASURA_ASUNTO = (
    'descuento OR exclusiva OR rebaja OR cyber OR "ultimos dias" OR '
    '"últimos días" OR gratis OR webinar OR curso OR newsletter OR noticias'
)

CONSULTAS = [
    ("Asunto de proceso",
     'subject:(entrevista OR postulacion OR postulación OR candidatura OR '
     '"proceso de seleccion" OR "proceso de selección" OR "oferta laboral" OR '
     '"oferta de trabajo" OR "propuesta laboral" OR "citacion" OR "citación") '
     '-from:(%s) -subject:(%s)' % (PORTALES, BASURA_ASUNTO)),

    ("Invitacion a entrevista",
     '("agendar una entrevista" OR "agendar entrevista" OR '
     '"coordinar una entrevista" OR "coordinar entrevista" OR '
     '"te invitamos a una entrevista" OR "invitarte a una entrevista" OR '
     '"nos gustaria invitarte" OR "nos gustaría invitarte" OR '
     '"disponibilidad para una entrevista" OR "entrevista presencial" OR '
     '"entrevista virtual") -from:(%s) -subject:(%s)' % (PORTALES, BASURA_ASUNTO)),

    ("Seleccion u oferta formal",
     '("has sido seleccionado" OR "ha sido seleccionado" OR "fuiste seleccionado" OR '
     '"queremos ofrecerte" OR "extendemos una oferta" OR "carta de oferta" OR '
     '"oferta formal" OR "propuesta economica" OR "propuesta económica" OR '
     '"felicitaciones por tu postulacion" OR "felicitaciones por tu postulación" OR '
     '"avanzar en tu proceso" OR "avanzaste a la siguiente etapa") '
     '-from:(%s) -subject:(%s)' % (PORTALES, BASURA_ASUNTO)),

    ("Plataformas de reclutamiento",
     'from:(teamtailor-mail.com OR myworkdayjobs.com OR greenhouse.io OR lever.co OR '
     'smartrecruiters.com OR bamboohr.com OR recruitee.com OR workable.com OR '
     'sherlockhr.com OR airavirtual.com OR talent.icims.com OR ats.bizneo.com OR '
     'brazoderecho.com OR hiringroom.com)'),

    ("Pruebas tecnicas",
     '("prueba tecnica" OR "prueba técnica" OR "desafio tecnico" OR "desafío técnico" OR '
     '"test psicotecnico" OR "test psicotécnico" OR "entrevista tecnica" OR '
     '"entrevista técnica" OR "assessment" OR "prueba de conocimientos") '
     '-from:(%s) -subject:(%s)' % (PORTALES, BASURA_ASUNTO)),
]


def log(t=""):
    print(t, flush=True)


def autenticar():
    creds = Credentials.from_authorized_user_file(RUTA_TOKEN, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def ids_de(svc, q, tope=4000):
    out, token = [], None
    while len(out) < tope:
        r = svc.users().messages().list(
            userId="me", q=q, maxResults=500, pageToken=token).execute()
        out += [m["id"] for m in (r.get("messages") or [])]
        token = r.get("nextPageToken")
        if not token:
            break
    return out


def ruido_conocido():
    """Ids que la cache ya marco como boletin o promocion."""
    if not os.path.exists(RUTA_DB):
        return set()
    conn = sqlite3.connect("file:%s?mode=ro" % RUTA_DB.replace("\\", "/"), uri=True)
    malos = {r[0] for r in conn.execute(
        "SELECT id FROM mensajes WHERE boletin = 1 OR categoria = 2")}
    conn.close()
    return malos


def detalles(svc, lista):
    out = []
    for n, i in enumerate(lista, 1):
        try:
            m = svc.users().messages().get(
                userId="me", id=i, format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()
        except Exception:
            continue
        h = {x["name"]: x["value"] for x in m.get("payload", {}).get("headers", [])}
        out.append({
            "id": i,
            "de": h.get("From", ""),
            "asunto": h.get("Subject", "(sin asunto)"),
            "fecha": h.get("Date", ""),
        })
        if n % 50 == 0:
            log("   leidos %d de %d..." % (n, len(lista)))
    return out


def main():
    ap = argparse.ArgumentParser(description="Busca ofertas, entrevistas y procesos de seleccion.")
    ap.add_argument("--listar", action="store_true", help="muestra lo que encontraria")
    ap.add_argument("--csv", metavar="ARCHIVO", help="guarda la lista en un CSV")
    ap.add_argument("--etiquetar", metavar="NOMBRE", help="nombre de la etiqueta a aplicar")
    ap.add_argument("--aplicar", action="store_true", help="lo hace de verdad")
    ap.add_argument("--si", action="store_true", help="no pide confirmacion")
    args = ap.parse_args()

    if not (args.listar or args.etiquetar):
        log("Indica --listar o --etiquetar NOMBRE.")
        return

    svc = autenticar()
    malos = ruido_conocido()

    encontrados = {}
    log("")
    log("%-32s %8s %8s" % ("BUSQUEDA", "CRUDOS", "UTILES"))
    log("-" * 52)
    for nombre, q in CONSULTAS:
        crudos = ids_de(svc, q)
        utiles = [i for i in crudos if i not in malos]
        log("%-32s %8d %8d" % (nombre, len(crudos), len(utiles)))
        for i in utiles:
            encontrados.setdefault(i, []).append(nombre)
    log("-" * 52)
    log("%-32s %8s %8d" % ("TOTAL SIN REPETIR", "", len(encontrados)))

    lista = list(encontrados)
    if not lista:
        log("")
        log("No se encontro nada.")
        return

    log("")
    log("Leyendo remitente y asunto de los %d correos..." % len(lista))
    det = detalles(svc, lista)

    por_dominio = {}
    for d in det:
        dom = d["de"].split("@")[-1].rstrip(">").lower() if "@" in d["de"] else "?"
        por_dominio.setdefault(dom, []).append(d)

    log("")
    log("EMPRESAS Y PLATAFORMAS QUE TE ESCRIBIERON")
    log("-" * 62)
    for dom, ds in sorted(por_dominio.items(), key=lambda kv: -len(kv[1])):
        log("%-42s %4d" % (dom[:42], len(ds)))

    log("")
    log("LOS 40 MAS RECIENTES")
    log("-" * 100)
    for d in det[:40]:
        log("%-34s | %s" % (d["de"][:34], d["asunto"][:60]))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Fecha", "De", "Asunto", "Motivo", "Id"])
            for d in det:
                w.writerow([d["fecha"], d["de"], d["asunto"],
                            ", ".join(encontrados.get(d["id"], [])), d["id"]])
        log("")
        log("CSV guardado: %s" % args.csv)

    if not args.etiquetar:
        log("")
        log("Nada modificado. Para crear la etiqueta: --etiquetar \"%s\" --aplicar"
            % "Ofertas y entrevistas")
        return

    # ---- crear etiqueta y aplicarla ----
    nombre = args.etiquetar
    if not args.aplicar:
        log("")
        log("Se pondria la etiqueta '%s' a %d correos." % (nombre, len(lista)))
        log("Nada modificado. Agrega --aplicar.")
        return

    if not args.si:
        log("")
        r = input("Poner la etiqueta '%s' a %d correos? (s/n): "
                  % (nombre, len(lista))).strip().lower()
        if r not in ("s", "si", "sí", "y"):
            log("Cancelado.")
            return

    existentes = svc.users().labels().list(userId="me").execute().get("labels") or []
    lid = None
    for l in existentes:
        if l.get("name", "").lower() == nombre.lower():
            lid = l["id"]
            log("Etiqueta '%s' ya existia." % nombre)
    if not lid:
        creada = svc.users().labels().create(
            userId="me",
            body={"name": nombre, "labelListVisibility": "labelShow",
                  "messageListVisibility": "show"},
        ).execute()
        lid = creada["id"]
        log("Etiqueta '%s' creada." % nombre)

    hechos = 0
    for i in range(0, len(lista), 1000):
        trozo = lista[i:i + 1000]
        svc.users().messages().batchModify(
            userId="me", body={"ids": trozo, "addLabelIds": [lid]}).execute()
        hechos += len(trozo)
        log("   %d / %d" % (hechos, len(lista)))

    log("")
    log("Listo: %d correos con la etiqueta '%s'." % (hechos, nombre))
    log("Siguen en tu bandeja. No se archivo nada.")


if __name__ == "__main__":
    main()
