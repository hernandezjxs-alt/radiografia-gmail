/**
 * Radiografia de tu Gmail - version Apps Script (aplicacion web).
 *
 * Cada persona abre el enlace, autoriza el script con SU cuenta y ve el analisis de SU buzon.
 * Se publica con: Implementar > Nueva implementacion > Aplicacion web
 *   - Ejecutar como:      Usuario que accede a la aplicacion web
 *   - Quien tiene acceso: Cualquier usuario con una cuenta de Google
 *
 * Solo lee metadatos (permiso gmail.metadata): remitente, asunto, fecha, tamano y etiquetas.
 * No lee el contenido de los correos, no puede modificar ni borrar, y no guarda nada:
 * no usa hojas, propiedades ni ningun almacenamiento.
 *
 * IMPORTANTE: usa un proyecto de Apps Script SEPARADO del que envia el resumen de Telegram,
 * porque las propiedades del script (donde esta el token del bot) las comparte todo el proyecto.
 */

var API = 'https://gmail.googleapis.com/gmail/v1/users/me';

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Radiografia de tu Gmail')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function cabeceras_() {
  return { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() };
}

function pedir_(ruta) {
  var intento = 0;
  while (true) {
    var r = UrlFetchApp.fetch(API + ruta, { headers: cabeceras_(), muteHttpExceptions: true });
    var c = r.getResponseCode();
    if (c === 200) return JSON.parse(r.getContentText());
    if ((c === 429 || c >= 500) && ++intento <= 5) { Utilities.sleep(500 * Math.pow(2, intento)); continue; }
    throw new Error('Gmail respondio ' + c + ': ' + r.getContentText().substring(0, 200));
  }
}

/** Cuenta y etiquetas. */
function perfil() {
  var p = pedir_('/profile?fields=emailAddress,messagesTotal');
  var e = pedir_('/labels?fields=labels(id,name,type)');
  return { email: p.emailAddress, total: p.messagesTotal, etiquetas: e.labels || [] };
}

/** Ids de los correos mas recientes (sin spam ni papelera). limite 0 = todos. */
function listarIds(limite) {
  var ids = [], pagina = '';
  do {
    var q = '/messages?maxResults=500&fields=messages/id,nextPageToken' + (pagina ? '&pageToken=' + encodeURIComponent(pagina) : '');
    var r = pedir_(q);
    (r.messages || []).forEach(function (m) { ids.push(m.id); });
    pagina = r.nextPageToken || '';
  } while (pagina && (!limite || ids.length < limite));
  return limite ? ids.slice(0, limite) : ids;
}

/** Metadatos de un lote de ids, en paralelo. Devuelve objetos compactos. */
function lote(ids) {
  var campos = 'id,labelIds,internalDate,sizeEstimate,payload/headers';
  var cab = '&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=List-Unsubscribe';
  var salida = {}, pendientes = ids.slice(), intento = 0;

  while (pendientes.length && intento < 4) {
    var reqs = pendientes.map(function (id) {
      return { url: API + '/messages/' + id + '?format=metadata&fields=' + encodeURIComponent(campos) + cab,
               headers: cabeceras_(), muteHttpExceptions: true };
    });
    var resp = UrlFetchApp.fetchAll(reqs);
    var fallidos = [];
    resp.forEach(function (r, i) {
      if (r.getResponseCode() === 200) {
        var m = JSON.parse(r.getContentText());
        var h = {};
        ((m.payload && m.payload.headers) || []).forEach(function (x) { h[x.name.toLowerCase()] = x.value; });
        salida[pendientes[i]] = { l: m.labelIds || [], d: m.internalDate, s: m.sizeEstimate,
                                  f: h['from'] || '', a: h['subject'] || '', u: h['list-unsubscribe'] ? 1 : 0 };
      } else {
        fallidos.push(pendientes[i]);
      }
    });
    pendientes = fallidos;
    if (pendientes.length) { intento++; Utilities.sleep(1000 * intento); }
  }
  var lista = [];
  ids.forEach(function (id) { if (salida[id]) lista.push(salida[id]); });
  return lista;
}

// =========================================================================
//  ALERTAS POR TELEGRAM (cada persona vincula su propio chat)
//  Configuracion del DUENO (una vez), en Configuracion del proyecto >
//  Propiedades de la secuencia de comandos:
//     TELEGRAM_TOKEN     = token del bot compartido
//     TELEGRAM_BOT_USER  = usuario del bot, sin @ (ej: mi_bot_de_avisos_bot)
//  El token solo lo lee el codigo del servidor: nunca se envia a la pagina.
//  Cada persona guarda SU chat id y SUS horas en sus propias propiedades de usuario.
// =========================================================================

var HORAS_PERMITIDAS = [8, 13, 19, 21];

function dueno_(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function usuario_() { return PropertiesService.getUserProperties(); }

function tgApi_(metodo, payload) {
  var token = dueno_('TELEGRAM_TOKEN');
  if (!token) throw new Error('El administrador aun no configuro el bot de Telegram.');
  var r = UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/' + metodo, {
    method: 'post', payload: payload || {}, muteHttpExceptions: true
  });
  var cuerpo = {};
  try { cuerpo = JSON.parse(r.getContentText()); } catch (e) {}
  if (r.getResponseCode() !== 200 || !cuerpo.ok) {
    throw new Error('Telegram respondio ' + r.getResponseCode() + (cuerpo.description ? ': ' + cuerpo.description : ''));
  }
  return cuerpo.result;
}

/** Estado para pintar el panel. */
function tgInfo() {
  var u = usuario_();
  var chat = u.getProperty('TG_CHAT');
  var horas = JSON.parse(u.getProperty('TG_HORAS') || '[]');
  return {
    configurado: !!dueno_('TELEGRAM_TOKEN') && !!dueno_('TELEGRAM_BOT_USER'),
    bot: dueno_('TELEGRAM_BOT_USER') || '',
    vinculado: !!chat,
    chatOculto: chat ? '••••' + String(chat).slice(-4) : '',
    horas: horas,
    permitidas: HORAS_PERMITIDAS
  };
}

/** Codigo unico para enlazar: la persona abre t.me/BOT?start=CODIGO y pulsa Start. */
function tgCodigo() {
  var codigo = Utilities.getUuid().replace(/-/g, '').substring(0, 10);
  usuario_().setProperty('TG_CODIGO', codigo);
  return { codigo: codigo, url: 'https://t.me/' + dueno_('TELEGRAM_BOT_USER') + '?start=' + codigo };
}

/** Busca en los mensajes recientes del bot el /start con el codigo de esta persona. */
function tgVincular() {
  var u = usuario_();
  var codigo = u.getProperty('TG_CODIGO');
  if (!codigo) throw new Error('Primero pulsa «Abrir Telegram» para generar tu codigo.');
  var updates = tgApi_('getUpdates', { limit: 100, timeout: 0 });
  var chat = null;
  updates.forEach(function (up) {
    var m = up.message;
    if (m && m.text && m.text.indexOf(codigo) >= 0) chat = m.chat.id;
  });
  if (!chat) throw new Error('No vi tu mensaje. Abre el enlace, pulsa START en Telegram y vuelve a intentarlo.');
  u.setProperty('TG_CHAT', String(chat));
  u.deleteProperty('TG_CODIGO');
  tgApi_('sendMessage', { chat_id: chat, text: '✅ Telegram vinculado. Aquí recibirás tu resumen de Gmail.' });
  return tgInfo();
}

/** Envia un resumen ahora. */
function tgProbar() {
  var chat = usuario_().getProperty('TG_CHAT');
  if (!chat) throw new Error('Primero vincula tu Telegram.');
  tgApi_('sendMessage', { chat_id: chat, text: resumenTexto_(Date.now() - 24 * 3600 * 1000, true) });
  return true;
}

/** Programa los envios diarios de esta persona. */
function tgActivar(horas) {
  var u = usuario_();
  if (!u.getProperty('TG_CHAT')) throw new Error('Primero vincula tu Telegram.');
  horas = (horas || []).map(Number).filter(function (h) { return HORAS_PERMITIDAS.indexOf(h) >= 0; });
  if (!horas.length) throw new Error('Elige al menos una hora.');
  quitarTriggers_();
  horas.forEach(function (h) {
    ScriptApp.newTrigger('resumenUsuario').timeBased().everyDays(1).atHour(h).nearMinute(0).create();
  });
  u.setProperty('TG_HORAS', JSON.stringify(horas));
  u.setProperty('TG_ULTIMO', String(Date.now()));
  return tgInfo();
}

/** Quita los envios y desvincula el chat. */
function tgDesactivar() {
  quitarTriggers_();
  var u = usuario_();
  ['TG_CHAT', 'TG_HORAS', 'TG_ULTIMO', 'TG_CODIGO'].forEach(function (k) { u.deleteProperty(k); });
  return tgInfo();
}

function quitarTriggers_() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'resumenUsuario') ScriptApp.deleteTrigger(t);
  });
}

/** Lo ejecutan los disparadores, con la cuenta de cada persona. */
function resumenUsuario() {
  var u = usuario_();
  var chat = u.getProperty('TG_CHAT');
  if (!chat) return;
  var desde = parseInt(u.getProperty('TG_ULTIMO') || '0', 10) || (Date.now() - 24 * 3600 * 1000);
  var ahora = Date.now();
  tgApi_('sendMessage', { chat_id: chat, text: resumenTexto_(desde, false) });
  u.setProperty('TG_ULTIMO', String(ahora));
}

// ---- Resumen en texto, solo con metadatos (el permiso gmail.metadata no permite buscar) ----
function resumenTexto_(desdeMs, esPrueba) {
  var f = function (ms, fmt) { return Utilities.formatDate(new Date(ms), 'America/Santiago', fmt); };
  var m = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); };
  var perfil = pedir_('/profile?fields=emailAddress,messagesTotal');
  var sinLeer = pedir_('/labels/UNREAD?fields=messagesTotal').messagesTotal;
  var ids = pedir_('/messages?maxResults=100&fields=messages/id').messages || [];
  var nuevos = lote(ids.map(function (x) { return x.id; })).filter(function (x) { return parseInt(x.d, 10) >= desdeMs; });

  var cats = { CATEGORY_PERSONAL: ['👤', 'Principal'], CATEGORY_PROMOTIONS: ['🛍️', 'Promociones'],
               CATEGORY_SOCIAL: ['👥', 'Social'], CATEGORY_UPDATES: ['🔔', 'Notificaciones'], CATEGORY_FORUMS: ['💬', 'Foros'] };
  var porCat = {}, porRem = {}, sinLeerNuevos = 0;
  nuevos.forEach(function (x) {
    if (x.l.indexOf('UNREAD') >= 0) sinLeerNuevos++;
    Object.keys(cats).forEach(function (c) { if (x.l.indexOf(c) >= 0) porCat[c] = (porCat[c] || 0) + 1; });
    var mm = String(x.f).match(/^\s*"?([^"<]*?)"?\s*<.*>\s*$/);
    var nombre = ((mm && mm[1].trim()) ? mm[1].trim() : String(x.f).replace(/[<>]/g, '').trim()) || '(desconocido)';
    porRem[nombre] = (porRem[nombre] || 0) + 1;
  });
  var top = Object.keys(porRem).sort(function (a, b) { return porRem[b] - porRem[a]; }).slice(0, 5);
  var medallas = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'];

  var L = [];
  L.push('📬 Resumen de Gmail' + (esPrueba ? '  🧪 PRUEBA' : ''));
  L.push('👤 ' + perfil.emailAddress);
  L.push('🕒 ' + f(Date.now(), 'dd/MM/yyyy HH:mm'));
  L.push('━━━━━━━━━━━━━━━━━━━━', '');
  L.push('📊 BUZÓN');
  L.push('📨 ' + m(perfil.messagesTotal) + ' correos');
  L.push('🔴 ' + m(sinLeer) + ' sin leer (' + (perfil.messagesTotal ? (sinLeer * 100 / perfil.messagesTotal).toFixed(1).replace('.', ',') : '0') + '%)', '');
  L.push('🆕 NUEVOS (desde ' + f(desdeMs, 'dd/MM HH:mm') + ')');
  L.push('📥 ' + nuevos.length + (nuevos.length >= 100 ? '+' : '') + ' correos');
  L.push('🔴 ' + sinLeerNuevos + ' sin leer');
  var filas = Object.keys(cats).filter(function (c) { return porCat[c]; })
    .map(function (c) { return cats[c][0] + ' ' + cats[c][1] + ' ' + porCat[c]; });
  if (filas.length) { L.push(''); L.push(filas.join('\n')); }
  if (top.length) {
    L.push('', '🏆 QUIÉN MÁS ESCRIBIÓ');
    top.forEach(function (k, i) { L.push(medallas[i] + ' ' + porRem[k] + ' · ' + k.substring(0, 34)); });
  }
  return L.join('\n').substring(0, 4000);
}

// =========================================================================
//  MOVER A LA PAPELERA (opcional, desactivado por defecto)
//  Solo funciona si el administrador:
//    1) pone la propiedad del script PERMITIR_BORRADO = 1, y
//    2) usa el manifiesto "appsscript.con_borrado.json" (permiso gmail.modify).
//  Con el manifiesto de solo lectura el borrado falla con un error de permisos.
//  Solo mueve a la PAPELERA (se recupera 30 dias), nunca borra definitivamente,
//  y excluye los correos con estrella. Solo actua cuando la persona lo pide.
// =========================================================================

/** La pagina pregunta esto al cargar para saber si muestra los botones de papelera. */
function config() {
  return { borrado: dueno_('PERMITIR_BORRADO') === '1' };
}

function permiteBorrar_() {
  if (dueno_('PERMITIR_BORRADO') !== '1') throw new Error('El borrado no esta habilitado en esta version.');
}

function consultaRemitente_(email) {
  email = String(email || '').trim().toLowerCase();
  if (!/^[^\s<>"'()]+@[^\s<>"'()]+\.[^\s<>"'()]+$/.test(email)) throw new Error('Remitente no valido.');
  return 'from:' + email + ' -is:starred';
}

function idsPorConsulta_(q, tope) {
  var ids = [], pagina = '';
  do {
    var ruta = '/messages?maxResults=500&fields=messages/id,nextPageToken&q=' + encodeURIComponent(q) +
               (pagina ? '&pageToken=' + encodeURIComponent(pagina) : '');
    var r = pedir_(ruta);
    (r.messages || []).forEach(function (m) { ids.push(m.id); });
    pagina = r.nextPageToken || '';
  } while (pagina && ids.length < tope);
  return ids.slice(0, tope);
}

var TOPE_BORRADO = 5000;

/** Cuantos correos se moverian. No cambia nada. */
function contarRemitente(email) {
  permiteBorrar_();
  var ids = idsPorConsulta_(consultaRemitente_(email), TOPE_BORRADO);
  return { n: ids.length, tope: ids.length >= TOPE_BORRADO };
}

/** Mueve a la papelera todos los correos de ese remitente (sin estrella). */
function papeleraRemitente(email) {
  permiteBorrar_();
  var ids = idsPorConsulta_(consultaRemitente_(email), TOPE_BORRADO);
  for (var i = 0; i < ids.length; i += 1000) {
    var r = UrlFetchApp.fetch(API + '/messages/batchModify', {
      method: 'post', contentType: 'application/json', headers: cabeceras_(), muteHttpExceptions: true,
      payload: JSON.stringify({ ids: ids.slice(i, i + 1000), addLabelIds: ['TRASH'], removeLabelIds: ['INBOX'] })
    });
    if (r.getResponseCode() >= 300) throw new Error('Gmail respondio ' + r.getResponseCode() + ': ' + r.getContentText().substring(0, 200));
  }
  return { movidos: ids.length };
}
