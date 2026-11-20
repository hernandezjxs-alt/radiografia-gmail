/* analisis.js
 * Convierte los metadatos de Gmail en la estructura que lee el dashboard.
 * Es la misma logica que analizar_gmail.py, pero en JavaScript y sin servidor:
 * corre en el navegador de quien usa la pagina.
 * Sirve tambien en Node (module.exports) para poder probarlo.
 */
(function (raiz) {
  "use strict";

  var DIA_MS = 86400000;
  var CATEGORIAS = {
    CATEGORY_PERSONAL: 0, CATEGORY_SOCIAL: 1, CATEGORY_PROMOTIONS: 2,
    CATEGORY_UPDATES: 3, CATEGORY_FORUMS: 4
  };
  // etiquetas de sistema que no aportan al analisis (igual que ETIQUETAS_IGNORADAS en Python)
  var IGNORADAS = {
    INBOX: 1, UNREAD: 1, SENT: 1, DRAFT: 1, TRASH: 1, SPAM: 1, CHAT: 1,
    CATEGORY_PERSONAL: 1, CATEGORY_SOCIAL: 1, CATEGORY_PROMOTIONS: 1,
    CATEGORY_UPDATES: 1, CATEGORY_FORUMS: 1, IMPORTANT: 1, YELLOW_STAR: 1
  };

  /* ---------- cabeceras ---------- */
  function decodificarBytes(bytes, charset) {
    try { return new TextDecoder((charset || "utf-8").toLowerCase()).decode(bytes); }
    catch (e) { return new TextDecoder("utf-8").decode(bytes); }
  }

  /** Decodifica palabras codificadas RFC 2047: =?utf-8?B?...?= y =?iso-8859-1?Q?...?= */
  function decodificarCabecera(valor) {
    if (!valor) return "";
    var v = String(valor).replace(/(\?=)\s+(=\?)/g, "$1$2"); // las palabras contiguas se unen
    return v.replace(/=\?([^?]+)\?([bBqQ])\?([^?]*)\?=/g, function (_, cs, enc, texto) {
      try {
        var bytes;
        if (enc.toUpperCase() === "B") {
          var bin = atob(texto.replace(/\s/g, ""));
          bytes = new Uint8Array(bin.length);
          for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        } else {
          var q = texto.replace(/_/g, " ");
          var arr = [];
          for (var j = 0; j < q.length; j++) {
            if (q[j] === "=" && /^[0-9a-fA-F]{2}$/.test(q.substr(j + 1, 2))) {
              arr.push(parseInt(q.substr(j + 1, 2), 16)); j += 2;
            } else arr.push(q.charCodeAt(j));
          }
          bytes = new Uint8Array(arr);
        }
        return decodificarBytes(bytes, cs);
      } catch (e) { return texto; }
    });
  }

  function limpiarEspacios(t) { return String(t || "").replace(/\s+/g, " ").trim(); }

  /** "Nombre <correo@dominio>" -> {nombre, email} */
  function parsearDe(de) {
    var s = decodificarCabecera(de);
    var nombre = "", email = "";
    var m = s.match(/^\s*(.*?)\s*<([^>]*)>\s*$/);
    if (m) { nombre = m[1].replace(/^"|"$/g, ""); email = m[2]; }
    else if (s.indexOf("@") >= 0) { email = s.trim(); }
    else { nombre = s; }
    nombre = limpiarEspacios(nombre);
    email = (email || "").trim().toLowerCase();
    if (!nombre) nombre = email.split("@")[0] || "(sin remitente)";
    return { nombre: nombre.slice(0, 90), email: email.slice(0, 120) };
  }

  /** Respuesta de messages.get (format=metadata) -> fila plana */
  function filaDesdeMensaje(m) {
    var cab = {};
    var hs = (m.payload && m.payload.headers) || [];
    for (var i = 0; i < hs.length; i++) cab[(hs[i].name || "").toLowerCase()] = hs[i].value || "";
    var de = parsearDe(cab["from"] || "");
    var dominio = de.email.indexOf("@") >= 0 ? de.email.split("@").pop().slice(0, 90) : "(desconocido)";
    var etiquetas = m.labelIds || [];
    var categoria = 5;
    for (var k = 0; k < etiquetas.length; k++) {
      if (CATEGORIAS.hasOwnProperty(etiquetas[k])) { categoria = CATEGORIAS[etiquetas[k]]; break; }
    }
    return {
      fecha: parseInt(m.internalDate || "0", 10) || 0,
      asunto: limpiarEspacios(decodificarCabecera(cab["subject"] || "")).slice(0, 140),
      nombre: de.nombre, email: de.email, dominio: dominio,
      etiquetas: etiquetas,
      peso: parseInt(m.sizeEstimate || "0", 10) || 0,
      categoria: categoria,
      noleido: etiquetas.indexOf("UNREAD") >= 0 ? 1 : 0,
      boletin: cab["list-unsubscribe"] ? 1 : 0
    };
  }

  /* ---------- estructura del dashboard ---------- */
  /**
   * filas: salida de filaDesdeMensaje
   * catalogo: [{id, name, type}] de users.labels.list
   * cuenta: correo de la cuenta
   */
  function construirDatos(filas, catalogo, cuenta) {
    filas = filas.slice().sort(function (a, b) { return a.fecha - b.fecha; });
    var nombres = {};
    (catalogo || []).forEach(function (l) { nombres[l.id] = { n: l.name, tipo: l.type || "user" }; });

    // remitentes ordenados por volumen
    var cuenta_ = {}, info = {};
    filas.forEach(function (f) {
      cuenta_[f.email] = (cuenta_[f.email] || 0) + 1;
      if (!info[f.email]) info[f.email] = [f.nombre, f.email, f.dominio];
    });
    var orden = Object.keys(cuenta_).sort(function (a, b) { return cuenta_[b] - cuenta_[a]; });
    var indice = {};
    orden.forEach(function (e, i) { indice[e] = i; });
    var remitentes = orden.map(function (e) { return info[e]; });

    // etiquetas: mascara de bits (maximo 30)
    var uso = {};
    filas.forEach(function (f) {
      f.etiquetas.forEach(function (et) { if (!IGNORADAS[et]) uso[et] = (uso[et] || 0) + 1; });
    });
    var elegidas = Object.keys(uso).sort(function (a, b) { return uso[b] - uso[a]; }).slice(0, 30);
    var posicion = {};
    elegidas.forEach(function (e, i) { posicion[e] = i; });
    var etiquetas = elegidas.map(function (id) {
      var d = nombres[id];
      return { id: id, n: d ? d.n : id.replace("Label_", "Etiqueta "), tipo: d ? d.tipo : "user" };
    });

    var col = { f: [], h: [], p: [], r: [], c: [], u: [], a: [], b: [], e: [], s: [] };
    var peso = 0, noLeidos = 0, boletines = 0;
    filas.forEach(function (f) {
      peso += f.peso; noLeidos += f.noleido; boletines += f.boletin;
      col.f.push(f.fecha ? Math.floor(f.fecha / DIA_MS) : 0);
      col.h.push(f.fecha ? Math.floor(f.fecha / 3600000) % 24 : 0);
      col.p.push(f.peso);
      col.r.push(indice[f.email]);
      col.c.push(f.categoria);
      col.u.push(f.noleido);
      col.a.push(f.peso >= 1000000 ? 1 : 0);
      col.b.push(f.boletin);
      var mascara = 0;
      f.etiquetas.forEach(function (et) { if (posicion.hasOwnProperty(et)) mascara |= (1 << posicion[et]); });
      col.e.push(mascara);
      col.s.push(f.asunto);
    });

    var validas = col.f.filter(function (x) { return x > 0; });
    var d = new Date();
    var dos = function (n) { return (n < 10 ? "0" : "") + n; };
    return {
      generado: dos(d.getDate()) + "/" + dos(d.getMonth() + 1) + "/" + d.getFullYear() + " " + dos(d.getHours()) + ":" + dos(d.getMinutes()),
      cuenta: cuenta || "",
      total: filas.length,
      peso: peso,
      noLeidos: noLeidos,
      conAdjunto: col.a.reduce(function (s, x) { return s + x; }, 0),
      boletines: boletines,
      desde: validas.length ? Math.min.apply(null, validas) * DIA_MS : 0,
      hasta: validas.length ? Math.max.apply(null, validas) * DIA_MS : 0,
      remitentes: remitentes,
      etiquetas: etiquetas,
      c: col
    };
  }

  var API = { decodificarCabecera: decodificarCabecera, parsearDe: parsearDe,
              filaDesdeMensaje: filaDesdeMensaje, construirDatos: construirDatos };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else raiz.AnalisisGmail = API;
})(typeof window !== "undefined" ? window : this);
