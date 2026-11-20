# -*- coding: utf-8 -*-
"""
Envia a Telegram un resumen de tu buzon (estado actual + lo nuevo de los ultimos dias).

Lee la cache local. Con --sincronizar la pone al dia primero, asi el resumen
refleja Gmail de hoy.

Configuracion: notificar.json (misma carpeta), bloque "telegram":
    { "telegram": { "token": "123456:AAH...", "chat": "123456789" } }

Uso:
    python resumen_telegram.py --sincronizar            # pone al dia y envia
    python resumen_telegram.py --simular                # muestra el mensaje, no envia
    python resumen_telegram.py --dias 1                 # resumen diario (por defecto 7)
    python resumen_telegram.py --buscar-chat            # encuentra tu chat id (escribele antes "hola" al bot)
    python resumen_telegram.py --importante "Ofertas y entrevistas"

Para recibirlo solo, programa el .bat de programar_resumen_telegram.bat.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.path.join(BASE, "cache_gmail.db")
RUTA_CONFIG = os.path.join(BASE, "notificar.json")
RUTA_SYNC = os.path.join(BASE, "sincronizar.py")

CATS = ["Principal", "Social", "Promociones", "Notificaciones", "Foros", "Otros"]


def miles(n):
    return "{:,}".format(int(n)).replace(",", ".")


def tam(b):
    mb = b / 1048576.0
    if mb >= 1024:
        return ("%.1f GB" % (mb / 1024)).replace(".", ",")
    return "%s MB" % miles(round(mb))


def config_telegram():
    if not os.path.exists(RUTA_CONFIG):
        sys.exit("Falta notificar.json. Copia notificar.json.ejemplo, deja solo el bloque 'telegram' y rellena token y chat.")
    with open(RUTA_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f).get("telegram") or {}
    return cfg


def api(token, metodo, datos=None):
    url = "https://api.telegram.org/bot%s/%s" % (token, metodo)
    cuerpo = urllib.parse.urlencode(datos).encode() if datos else None
    with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def buscar_chat(token):
    r = api(token, "getUpdates")
    vistos = {}
    for u in r.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        ch = m.get("chat") or {}
        if ch.get("id"):
            vistos[ch["id"]] = ch.get("first_name") or ch.get("title") or ""
    if not vistos:
        print("No hay mensajes. Abre tu bot en Telegram, pulsa Start o escribe 'hola' y repite.")
        return
    for cid, nombre in vistos.items():
        print("chat id: %s   (%s)" % (cid, nombre))
    print("Copia ese numero al campo 'chat' de notificar.json.")


def construir(dias, importante):
    c = sqlite3.connect(RUTA_DB)
    ahora_ms = int(time.time() * 1000)
    desde = ahora_ms - dias * 86400000

    total, peso, noleidos = c.execute("SELECT COUNT(*), COALESCE(SUM(peso),0), COALESCE(SUM(noleido),0) FROM mensajes").fetchone()
    if not total:
        return "La cache esta vacia. Ejecuta primero analizar_gmail.py."

    nuevos, nuevos_nl = c.execute(
        "SELECT COUNT(*), COALESCE(SUM(noleido),0) FROM mensajes WHERE fecha >= ?", (desde,)).fetchone()
    por_cat = dict(c.execute("SELECT categoria, COUNT(*) FROM mensajes WHERE fecha >= ? GROUP BY categoria", (desde,)).fetchall())
    top = c.execute(
        """SELECT COALESCE(NULLIF(nombre,''), email), COUNT(*) n FROM mensajes
           WHERE fecha >= ? GROUP BY email ORDER BY n DESC LIMIT 5""", (desde,)).fetchall()
    viejas = c.execute(
        """SELECT COUNT(*), COALESCE(SUM(peso),0) FROM mensajes
           WHERE categoria = 2 AND fecha < ?""", (ahora_ms - 365 * 86400000,)).fetchone()

    cuenta = ""
    try:
        with open(os.path.join(BASE, "datos_gmail.js"), encoding="utf-8") as f:
            cabecera = f.read(400)
        if '"cuenta":"' in cabecera:
            cuenta = cabecera.split('"cuenta":"')[1].split('"')[0]
    except Exception:
        pass

    L = []
    L.append("Resumen de Gmail" + (" - " + cuenta if cuenta else ""))
    L.append(time.strftime("%d/%m/%Y %H:%M"))
    L.append("")
    L.append("BUZON")
    L.append("%s correos  |  %s" % (miles(total), tam(peso)))
    L.append("%s sin leer (%s%%)" % (miles(noleidos), ("%.1f" % (noleidos * 100.0 / total)).replace(".", ",")))
    L.append("")
    etiqueta_dias = "ultimas 24 h" if dias == 1 else "ultimos %d dias" % dias
    L.append("NUEVOS (%s)" % etiqueta_dias)
    L.append("%s correos, %s sin leer" % (miles(nuevos), miles(nuevos_nl)))
    partes = ["%s %s" % (CATS[k], miles(v)) for k, v in sorted(por_cat.items(), key=lambda x: -x[1]) if 0 <= k < 6]
    if partes:
        L.append(" / ".join(partes))
    if top:
        L.append("")
        L.append("Quien mas escribio:")
        for nombre, n in top:
            L.append("  %s  %s" % (miles(n), (nombre or "?")[:34]))

    # etiqueta que no te puedes perder (por defecto ofertas y entrevistas)
    if importante:
        fila = c.execute("SELECT id FROM etiquetas WHERE nombre = ?", (importante,)).fetchone()
        if fila:
            lid = fila[0]
            coinc = c.execute(
                """SELECT asunto, COALESCE(NULLIF(nombre,''), email) FROM mensajes
                   WHERE fecha >= ? AND (',' || etiquetas || ',') LIKE ? ORDER BY fecha DESC LIMIT 6""",
                (desde, "%," + lid + ",%")).fetchall()
            L.append("")
            if coinc:
                L.append("%s (%d nuevos)" % (importante.upper(), len(coinc)))
                for asunto, quien in coinc:
                    L.append("  - %s (%s)" % ((asunto or "(sin asunto)")[:60], quien[:24]))
            else:
                L.append("%s: nada nuevo" % importante)

    if viejas[0]:
        L.append("")
        L.append("LIMPIEZA POSIBLE")
        L.append("%s promociones de mas de 1 ano (%s)" % (miles(viejas[0]), tam(viejas[1])))
    c.close()
    return "\n".join(L)[:4000]


def main():
    ap = argparse.ArgumentParser(description="Resumen de Gmail por Telegram")
    ap.add_argument("--sincronizar", action="store_true", help="pone al dia la cache antes de resumir")
    ap.add_argument("--simular", action="store_true", help="muestra el mensaje y no lo envia")
    ap.add_argument("--dias", type=int, default=7, help="ventana de 'nuevos' (1 = resumen diario)")
    ap.add_argument("--importante", default="Ofertas y entrevistas", help="etiqueta a destacar ('' para quitarla)")
    ap.add_argument("--buscar-chat", action="store_true", help="muestra tu chat id")
    a = ap.parse_args()

    if a.buscar_chat:
        buscar_chat(config_telegram().get("token", ""))
        return

    if a.sincronizar:
        print("Sincronizando con Gmail...", flush=True)
        r = subprocess.run([sys.executable, "-W", "ignore", RUTA_SYNC], cwd=BASE)
        if r.returncode != 0:
            sys.exit("La sincronizacion fallo; no se envia el resumen. Si dice invalid_grant, mira la seccion 9.4 de la guia.")

    texto = construir(a.dias, a.importante)
    print(texto)
    if a.simular:
        print("\n(simulacion: no se envio nada)")
        return

    cfg = config_telegram()
    if not cfg.get("token") or not cfg.get("chat") or "PEGA_AQUI" in cfg["token"] + str(cfg["chat"]):
        sys.exit("Completa 'token' y 'chat' en notificar.json (bloque telegram).")
    try:
        r = api(cfg["token"], "sendMessage", {"chat_id": cfg["chat"], "text": texto})
        print("\nEnviado a Telegram." if r.get("ok") else "\nTelegram respondio: %s" % r)
    except Exception as e:
        sys.exit("No se pudo enviar: %s" % e)


if __name__ == "__main__":
    main()
