/* cargador.js
 * Inicio de sesion con Google, descarga de metadatos de Gmail y arranque del dashboard.
 * Todo ocurre en el navegador de la persona. No hay servidor propio: los datos van
 * de Google al navegador y no se guardan en ningun sitio.
 *
 * Permiso que pide: gmail.metadata (cabeceras, etiquetas, tamanos). No lee el cuerpo
 * de los correos y no puede modificar ni borrar nada.
 */
(function () {
  "use strict";

  var SCOPE = "https://www.googleapis.com/auth/gmail.metadata";
  var API = "https://gmail.googleapis.com/gmail/v1/users/me";
  var CONCURRENCIA = 12;

  var $ = function (s) { return document.querySelector(s); };
  var token = null, tokenClient = null, cancelado = false;

  function miles(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  function esperar(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function estado(texto, error) {
    var e = $("#loginEstado");
    e.textContent = texto || "";
    e.style.color = error ? "#fb7185" : "";
  }
  function progreso(hecho, total, extra) {
    var pc = total ? Math.min(100, Math.round(hecho * 100 / total)) : 0;
    $("#loginBarra").style.width = pc + "%";
    $("#loginProgreso").textContent = miles(hecho) + " de " + miles(total) + " (" + pc + "%)" + (extra ? " · " + extra : "");
  }

  /* ---------- autenticacion ---------- */
  function clienteConfigurado() {
    var id = window.GMAIL_CLIENT_ID || "";
    return id && id.indexOf("PEGA_AQUI") < 0;
  }

  function pedirToken(silencioso) {
    return new Promise(function (resolver, rechazar) {
      if (!window.google || !google.accounts || !google.accounts.oauth2) {
        return rechazar(new Error("No se cargó el servicio de inicio de sesión de Google. Revisa tu conexión o desactiva el bloqueador de anuncios y recarga."));
      }
      if (!tokenClient) {
        tokenClient = google.accounts.oauth2.initTokenClient({
          client_id: window.GMAIL_CLIENT_ID,
          scope: SCOPE,
          callback: function () {}
        });
      }
      tokenClient.callback = function (r) {
        if (r && r.error) return rechazar(new Error(r.error_description || r.error));
        token = r.access_token;
        resolver(token);
      };
      tokenClient.error_callback = function (e) {
        rechazar(new Error(e && e.type === "popup_closed" ? "Cerraste la ventana de Google antes de autorizar." :
          "No se pudo abrir la ventana de Google (" + (e && e.type || "error") + "). Permite las ventanas emergentes para este sitio."));
      };
      tokenClient.requestAccessToken({ prompt: silencioso ? "" : "select_account" });
    });
  }

  /* ---------- API de Gmail, con reintentos ---------- */
  async function api(ruta, params, reintentoToken) {
    var url = API + ruta;
    if (params) {
      var q = new URLSearchParams();
      Object.keys(params).forEach(function (k) {
        [].concat(params[k]).forEach(function (v) { q.append(k, v); });
      });
      url += "?" + q.toString();
    }
    var intento = 0;
    while (true) {
      if (cancelado) throw new Error("cancelado");
      var r;
      try { r = await fetch(url, { headers: { Authorization: "Bearer " + token } }); }
      catch (e) { r = null; }
      if (r && r.ok) return r.json();
      var codigo = r ? r.status : 0;
      if (codigo === 401 && !reintentoToken) {          // el token dura 1 hora
        await pedirToken(true);
        return api(ruta, params, true);
      }
      var detalle = "", motivo = "";
      if (r) { try { var cuerpo = (await r.json()).error || {}; detalle = cuerpo.message || ""; motivo = ((cuerpo.errors || [])[0] || {}).reason || ""; } catch (e) {} }
      // 403 solo se reintenta si es limite de cuota; si es de permisos, falla enseguida
      var reintentable = codigo === 0 || codigo === 429 || codigo >= 500 || (codigo === 403 && /ratelimit/i.test(motivo));
      if (!reintentable || ++intento > 6) {
        throw new Error("Gmail respondió " + codigo + (detalle ? ": " + detalle : ""));
      }
      await esperar(Math.min(15000, 600 * Math.pow(2, intento)) + Math.random() * 400);
    }
  }

  async function listarIds(limite) {
    var ids = [], pagina = null;
    do {
      var r = await api("/messages", { maxResults: 500, pageToken: pagina || [], fields: "messages/id,nextPageToken" });
      (r.messages || []).forEach(function (m) { ids.push(m.id); });
      pagina = r.nextPageToken;
      estado("Contando tu buzón… " + miles(ids.length) + " correos");
    } while (pagina && (!limite || ids.length < limite));
    return limite ? ids.slice(0, limite) : ids;
  }

  async function descargar(ids) {
    var filas = new Array(ids.length), siguiente = 0, hechos = 0, fallidos = 0;
    var inicio = Date.now();
    async function trabajador() {
      while (!cancelado) {
        var i = siguiente++;
        if (i >= ids.length) return;
        try {
          var m = await api("/messages/" + ids[i], {
            format: "metadata",
            metadataHeaders: ["From", "Subject", "List-Unsubscribe"],
            fields: "id,labelIds,internalDate,sizeEstimate,payload/headers"
          });
          filas[i] = AnalisisGmail.filaDesdeMensaje(m);
        } catch (e) {
          if (e.message === "cancelado") return;
          fallidos++;
        }
        hechos++;
        if (hechos % 25 === 0 || hechos === ids.length) {
          var seg = (Date.now() - inicio) / 1000, ritmo = hechos / Math.max(seg, 1);
          var resta = Math.round((ids.length - hechos) / Math.max(ritmo, 0.1));
          progreso(hechos, ids.length, resta > 60 ? "faltan ~" + Math.ceil(resta / 60) + " min" : "faltan ~" + resta + " s");
        }
      }
    }
    var pool = [];
    for (var k = 0; k < CONCURRENCIA; k++) pool.push(trabajador());
    await Promise.all(pool);
    if (cancelado) throw new Error("cancelado");
    return { filas: filas.filter(Boolean), fallidos: fallidos };
  }

  /* ---------- flujo principal ---------- */
  async function analizar() {
    if (!clienteConfigurado()) {
      estado("Falta configurar el ID de cliente de Google en config.js (ver instrucciones abajo).", true);
      $("#loginConfig").classList.remove("oculto");
      return;
    }
    cancelado = false;
    $("#btnConectar").disabled = true;
    $("#btnCancelar").classList.remove("oculto");
    $("#loginBarraCaja").classList.remove("oculto");
    try {
      estado("Abriendo la ventana de Google…");
      await pedirToken(false);
      estado("Leyendo tu cuenta…");
      var perfil = await api("/profile", { fields: "emailAddress,messagesTotal" });
      var etiquetas = (await api("/labels", { fields: "labels(id,name,type)" })).labels || [];
      var limite = parseInt($("#loginLimite").value, 10) || 0;
      var ids = await listarIds(limite);
      if (!ids.length) throw new Error("Esta cuenta no tiene correos para analizar.");
      estado("Descargando cabeceras de " + miles(ids.length) + " correos. Deja esta pestaña abierta.");
      var r = await descargar(ids);
      estado("Analizando…");
      await esperar(30);
      var datos = AnalisisGmail.construirDatos(r.filas, etiquetas, perfil.emailAddress);
      window.DATOS_GMAIL = datos;
      $("#login").classList.add("oculto");
      $("#app").classList.remove("oculto");
      window.arrancarDashboard();
      var nota = [];
      if (limite && perfil.messagesTotal > ids.length) nota.push("análisis de los " + miles(ids.length) + " correos más recientes de " + miles(perfil.messagesTotal));
      if (r.fallidos) nota.push(miles(r.fallidos) + " no se pudieron leer");
      if (nota.length) $("#generado").textContent += " · " + nota.join(" · ");
      agregarDesconectar();
    } catch (e) {
      $("#btnConectar").disabled = false;
      $("#btnCancelar").classList.add("oculto");
      estado(e.message === "cancelado" ? "Cancelado." : (e.message || String(e)), e.message !== "cancelado");
    }
  }

  function agregarDesconectar() {
    var cont = document.querySelector("header.topo > div:last-child");
    if (!cont || document.getElementById("btnDesconectar")) return;
    var b = document.createElement("button");
    b.className = "btn"; b.id = "btnDesconectar";
    b.title = "Revoca el permiso a esta página y borra los datos de la pantalla";
    b.textContent = "Desconectar";
    b.addEventListener("click", function () {
      var fin = function () { location.reload(); };
      try { google.accounts.oauth2.revoke(token, fin); } catch (e) { fin(); }
      setTimeout(fin, 1500);
    });
    cont.appendChild(b);
  }

  document.addEventListener("DOMContentLoaded", function () {
    $("#btnConectar").addEventListener("click", analizar);
    $("#btnCancelar").addEventListener("click", function () { cancelado = true; });
    if (!clienteConfigurado()) $("#loginConfig").classList.remove("oculto");
  });
})();
