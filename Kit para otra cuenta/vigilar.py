# -*- coding: utf-8 -*-
"""
Vigila la descarga de Gmail y avisa al celular cuando termina.

Se encarga de todo sin que estes pendiente:
  1. Espera a que termine cualquier descarga que ya este corriendo.
  2. Si faltan correos, vuelve a ejecutar la descarga (retoma solo los que faltan).
  3. Regenera el dashboard y el reporte con los datos completos.
  4. Envia un aviso a Telegram o por correo con el resumen final.

Uso:
    python vigilar.py            # vigila y avisa al terminar
    python vigilar.py --probar   # solo prueba el envio del aviso

Configuracion: archivo notificar.json (misma carpeta).
"""
import json
import os
import smtplib
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from email.message import EmailMessage

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.path.join(BASE, "cache_gmail.db")
RUTA_CONFIG = os.path.join(BASE, "notificar.json")
RUTA_LOG = os.path.join(BASE, "aviso.log")
SCRIPT = os.path.join(BASE, "analizar_gmail.py")

TOTAL_ESPERADO = 36048
MAX_RONDAS = 8


def log(texto):
    linea = "%s  %s" % (time.strftime("%H:%M:%S"), texto)
    print(linea, flush=True)
    try:
        with open(RUTA_LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s  %s\n" % (time.strftime("%d/%m/%Y"), time.strftime("%H:%M:%S"), texto))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Estado de la descarga
# --------------------------------------------------------------------------- #
def en_cache():
    """Cuenta los correos ya guardados (0 si la base aun no existe)."""
    if not os.path.exists(RUTA_DB):
        return 0
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % RUTA_DB.replace("\\", "/"),
                               uri=True, timeout=10)
        n = conn.execute("SELECT COUNT(*) FROM mensajes").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def resumen_db():
    """Datos para el mensaje final."""
    datos = {"total": 0, "noleidos": 0, "gb": 0.0, "top": "", "top_n": 0, "anios": ""}
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % RUTA_DB.replace("\\", "/"),
                               uri=True, timeout=10)
        datos["total"] = conn.execute("SELECT COUNT(*) FROM mensajes").fetchone()[0]
        datos["noleidos"] = conn.execute(
            "SELECT COUNT(*) FROM mensajes WHERE noleido=1").fetchone()[0]
        peso = conn.execute("SELECT SUM(peso) FROM mensajes").fetchone()[0] or 0
        datos["gb"] = peso / 1073741824.0
        fila = conn.execute(
            "SELECT nombre, COUNT(*) c FROM mensajes GROUP BY nombre "
            "ORDER BY c DESC LIMIT 1").fetchone()
        if fila:
            datos["top"], datos["top_n"] = fila[0], fila[1]
        mn, mx = conn.execute("SELECT MIN(fecha), MAX(fecha) FROM mensajes").fetchone()
        if mn and mx:
            a1 = time.gmtime(mn / 1000.0).tm_year
            a2 = time.gmtime(mx / 1000.0).tm_year
            datos["anios"] = "%s a %s" % (a1, a2)
        conn.close()
    except Exception:
        pass
    return datos


def descarga_activa():
    """True si ya hay un analizar_gmail.py corriendo en otra ventana."""
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*analizar_gmail*' } | "
             "Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=60)
        return int((salida.stdout or "0").strip() or 0) > 0
    except Exception:
        return False


def ejecutar_descarga():
    """Lanza una pasada de descarga y deja su salida en el log."""
    log("Lanzando descarga (retoma solo los correos que faltan)...")
    with open(RUTA_LOG, "a", encoding="utf-8") as f:
        f.write("\n--- pasada de descarga ---\n")
        subprocess.run(
            [sys.executable, SCRIPT, "--lote", "50", "--pausa", "1.2", "--no-abrir"],
            cwd=BASE, stdout=f, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def regenerar_salidas():
    log("Regenerando dashboard y reporte con los datos completos...")
    with open(RUTA_LOG, "a", encoding="utf-8") as f:
        subprocess.run(
            [sys.executable, SCRIPT, "--resumen", "--no-abrir"],
            cwd=BASE, stdout=f, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))


# --------------------------------------------------------------------------- #
# Envio del aviso
# --------------------------------------------------------------------------- #
def cargar_config():
    if not os.path.exists(RUTA_CONFIG):
        return {}
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log("No pude leer notificar.json (%s)" % e)
        return {}


def enviar_telegram(cfg, texto):
    token = cfg.get("token", "").strip()
    chat = str(cfg.get("chat", "")).strip()
    if not token or not chat:
        return False, "faltan token o chat"
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    cuerpo = urllib.parse.urlencode({
        "chat_id": chat, "text": texto, "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(url, data=cuerpo, timeout=30) as r:
            ok = json.loads(r.read().decode()).get("ok", False)
        return (True, "enviado") if ok else (False, "Telegram respondio ok=false")
    except Exception as e:
        return False, str(e)


def enviar_correo(cfg, texto):
    usuario = cfg.get("usuario", "").strip()
    clave = cfg.get("clave_app", "").strip()
    destino = cfg.get("destino", "").strip() or usuario
    servidor = cfg.get("servidor", "smtp.gmail.com")
    puerto = int(cfg.get("puerto", 587))
    if not usuario or not clave:
        return False, "faltan usuario o clave_app"
    msg = EmailMessage()
    msg["From"] = usuario
    msg["To"] = destino
    msg["Subject"] = "Dashboard Gmail: descarga terminada"
    msg.set_content(texto)
    try:
        with smtplib.SMTP(servidor, puerto, timeout=45) as s:
            s.starttls()
            s.login(usuario, clave)
            s.send_message(msg)
        return True, "enviado"
    except Exception as e:
        return False, str(e)


def avisar(texto):
    cfg = cargar_config()
    enviados = []

    if cfg.get("telegram"):
        ok, detalle = enviar_telegram(cfg["telegram"], texto)
        log("Telegram: %s" % ("ENVIADO" if ok else "fallo - " + detalle))
        if ok:
            enviados.append("telegram")

    if cfg.get("correo"):
        ok, detalle = enviar_correo(cfg["correo"], texto)
        log("Correo: %s" % ("ENVIADO" if ok else "fallo - " + detalle))
        if ok:
            enviados.append("correo")

    # Siempre deja el aviso en un archivo, por si nada mas funciona
    try:
        with open(os.path.join(BASE, "AVISO_TERMINADO.txt"), "w", encoding="utf-8") as f:
            f.write(texto + "\n")
    except Exception:
        pass

    if not enviados:
        log("No se pudo enviar por ningun canal. Revisa notificar.json")
    return enviados


# --------------------------------------------------------------------------- #
# Programa principal
# --------------------------------------------------------------------------- #
def main():
    probar = "--probar" in sys.argv

    if probar:
        log("Modo prueba: enviando aviso de ejemplo...")
        texto = ("PRUEBA - Dashboard Gmail\n\n"
                 "Si recibes este mensaje, el aviso automatico funciona.\n"
                 "Te llegara otro igual cuando termine la descarga de los %s correos."
                 % "{:,}".format(TOTAL_ESPERADO).replace(",", "."))
        avisos = avisar(texto)
        log("Resultado: %s" % (", ".join(avisos) if avisos else "sin canales configurados"))
        return

    log("Vigilando la descarga. Total esperado: %s correos."
        % "{:,}".format(TOTAL_ESPERADO).replace(",", "."))

    ronda = 0
    while ronda < MAX_RONDAS:
        if descarga_activa():
            log("Hay una descarga en curso. Espero a que termine...")
            while descarga_activa():
                time.sleep(30)
            log("La descarga en curso termino.")

        n = en_cache()
        log("Correos en cache: %s" % "{:,}".format(n).replace(",", "."))
        if n >= TOTAL_ESPERADO:
            break

        ronda += 1
        log("Faltan %s. Ronda %d de %d."
            % ("{:,}".format(TOTAL_ESPERADO - n).replace(",", "."), ronda, MAX_RONDAS))
        ejecutar_descarga()
        time.sleep(10)

    n = en_cache()
    regenerar_salidas()
    d = resumen_db()

    completo = n >= TOTAL_ESPERADO
    if completo:
        texto = (
            "LISTO - Dashboard Gmail\n\n"
            "Ya estan los {total} correos completos.\n\n"
            "Sin leer: {nl} ({pct}%)\n"
            "Espacio: {gb} GB\n"
            "Anios: {anios}\n"
            "Mayor remitente: {top} ({topn} correos)\n\n"
            "Dashboard:\n"
            "Escritorio\\OpenCode\\Dashboard Gmail\\dashboard.html"
        )
    else:
        texto = (
            "PARCIAL - Dashboard Gmail\n\n"
            "Se descargaron {total} de {esp} correos.\n"
            "Faltan {falta}. Google limito las peticiones; se puede reintentar despues.\n\n"
            "Sin leer: {nl}\n"
            "Lo descargado ya esta en el dashboard."
        )

    texto = texto.format(
        total="{:,}".format(d["total"]).replace(",", "."),
        esp="{:,}".format(TOTAL_ESPERADO).replace(",", "."),
        falta="{:,}".format(max(0, TOTAL_ESPERADO - d["total"])).replace(",", "."),
        nl="{:,}".format(d["noleidos"]).replace(",", "."),
        pct=round(d["noleidos"] * 100.0 / d["total"], 1) if d["total"] else 0,
        gb=round(d["gb"], 2),
        anios=d["anios"] or "sin datos",
        top=d["top"] or "sin datos",
        topn="{:,}".format(d["top_n"]).replace(",", "."),
    )

    log("Aviso final:")
    log(texto)
    avisar(texto)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FALLO el vigilante:\n" + traceback.format_exc())
        avisar("El vigilante de Gmail fallo. Revisa aviso.log en la carpeta Dashboard Gmail.")
