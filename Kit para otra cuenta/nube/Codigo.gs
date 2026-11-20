/**
 * Resumen de Gmail por Telegram, ejecutado en la nube de Google (no necesita tu PC).
 * Envia un mensaje con analisis y 4 graficas de fondo oscuro:
 *   1) bandejas (dona)  2) leidos / sin leer (dona)  3) quien mas escribio (dona)  4) tendencia de 30 dias
 *
 * Pasos (el detalle esta en la guia, seccion 11.5):
 *   1. https://script.google.com -> Proyecto nuevo -> pega este codigo en Codigo.gs
 *   2. Servicios (+) -> agrega "Gmail API"   (o pega appsscript.json)
 *   3. Configuracion del proyecto -> Propiedades de la secuencia de comandos:
 *        TELEGRAM_TOKEN = el token de tu bot
 *        TELEGRAM_CHAT  = tu chat id
 *   4. Ejecuta probar() y autoriza. Debe llegarte el mensaje con las graficas.
 *   5. Ejecuta programar() una vez: crea los envios diarios.
 *
 * Usa la cuenta de Gmail con la que abres el script. No usa tokens de IA.
 * Las graficas las dibuja el servicio Charts de Google: no se envia nada a terceros.
 */

// ---- AJUSTES -------------------------------------------------------------
var HORAS = [19, 21];                    // horas del dia (hora de ZONA)
var ZONA = 'America/Santiago';           // zona horaria de los envios
var ETIQUETA_IMPORTANTE = 'Ofertas y entrevistas'; // '' para no destacar ninguna
var VENTANA_INICIAL_HORAS = 24;          // la primera vez, cuanto mirar atras
var MAX_HILOS = 100;                     // tope de conversaciones a revisar
var CON_GRAFICAS = true;                 // false = solo texto
var BOTONES_BORRADO = true;              // botones "🗑️ Papelera" bajo el resumen (solo responde a TU chat)
var TOPE_HILOS_BORRADO = 2000;           // maximo de conversaciones que mueve de una vez
var DIAS_TENDENCIA = 30;                 // dias de la grafica de tendencia
var SEP = '━━━━━━━━━━━━━━━━━━━━';
// colores claros: el texto que dibuja Google dentro de los trozos sale oscuro y asi se lee sobre cada uno
var PALETA_DONA = ['#38bdf8', '#a78bfa', '#fb7185', '#fb923c', '#fbbf24', '#4ade80', '#cbd5e1'];
var CUADRO_DONA = ['🟦', '🟪', '🟥', '🟧', '🟨', '🟩', '⬜'];
var MEDALLA = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'];
var ICONO_BANDEJA = { 'Principal': '👤', 'Promociones': '🛍️', 'Social': '👥', 'Notificaciones': '🔔', 'Foros': '💬' };

// ---- PROGRAMACION --------------------------------------------------------
/** Crea los envios diarios. Ejecutar una sola vez (se puede repetir sin duplicar). */
function programar() {
  desprogramar();
  HORAS.forEach(function (h) {
    ScriptApp.newTrigger('resumen')
      .timeBased().everyDays(1).atHour(h).nearMinute(0).inTimezone(ZONA).create();
  });
  Logger.log('Programado a las ' + HORAS.join(' y ') + ' (' + ZONA + '). Google puede variar unos minutos.');
}

/** Quita los envios programados. */
function desprogramar() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'resumen') ScriptApp.deleteTrigger(t);
  });
}

/** Prueba: envia un resumen ahora, de las ultimas 24 h, sin tocar la marca de "desde el ultimo". */
function probar() {
  var desde = new Date(Date.now() - 24 * 3600 * 1000);
  enviarTodo_(construir_(desde, true));
}

/** Funcion que ejecutan los envios programados. */
function resumen() {
  var props = PropertiesService.getScriptProperties();
  var ultimo = props.getProperty('ULTIMO_ENVIO');
  var desde = ultimo ? new Date(parseInt(ultimo, 10))
                     : new Date(Date.now() - VENTANA_INICIAL_HORAS * 3600 * 1000);
  var ahora = Date.now();
  enviarTodo_(construir_(desde, false));
  props.setProperty('ULTIMO_ENVIO', String(ahora));   // solo si el envio no fallo
}

// ---- CONSTRUCCION DEL MENSAJE -------------------------------------------
/** Devuelve { texto, graficos: [{blob, pie}] } */
function construir_(desde, esPrueba) {
  var f = function (d, fmt) { return Utilities.formatDate(d, ZONA, fmt); };
  var L = [];
  var graficos = [];
  var cuenta = Session.getEffectiveUser().getEmail();
  L.push('📬 Resumen de Gmail' + (esPrueba ? '  🧪 PRUEBA' : ''));
  L.push('👤 ' + cuenta);
  L.push('🕒 ' + f(new Date(), 'dd/MM/yyyy HH:mm'));
  L.push(SEP);
  L.push('');

  // estado general del buzon
  try {
    var perfil = Gmail.Users.getProfile('me');
    var sinLeer = Gmail.Users.Labels.get('me', 'UNREAD').messagesTotal;
    var total = perfil.messagesTotal;
    L.push('📊 BUZÓN');
    L.push('📨 ' + miles_(total) + ' correos');
    L.push('🔴 ' + miles_(sinLeer) + ' sin leer (' + pct_(sinLeer, total) + '%)');
    L.push('');
  } catch (e) {
    L.push('📊 BUZÓN: ⚠️ no se pudo leer (' + e.message + ')');
    L.push('');
  }

  // correos nuevos desde la ultima vez
  var epoch = Math.floor(desde.getTime() / 1000);
  var hilos = GmailApp.search('after:' + epoch, 0, MAX_HILOS);
  var msgs = [];
  hilos.forEach(function (h) {
    h.getMessages().forEach(function (m) {
      if (m.getDate().getTime() >= desde.getTime()) msgs.push(m);
    });
  });
  var sinLeerNuevos = msgs.filter(function (m) { return m.isUnread(); }).length;
  L.push('🆕 NUEVOS (desde ' + f(desde, 'dd/MM HH:mm') + ')');
  L.push('📥 ' + msgs.length + ' correos');
  L.push('🔴 ' + sinLeerNuevos + ' sin leer (' + pct_(sinLeerNuevos, msgs.length) + '%)');

  // comparacion con el periodo anterior de igual duracion
  var dur = Date.now() - desde.getTime();
  var antes = contar_('after:' + Math.floor((desde.getTime() - dur) / 1000) + ' before:' + epoch);
  if (antes > 0) {
    var delta = Math.round((msgs.length - antes) * 100 / antes);
    L.push((delta > 0 ? '🔺' : delta < 0 ? '🔻' : '➖') + ' Periodo anterior: ~' + antes + ' conversaciones (' + (delta >= 0 ? '+' : '') + delta + '% ahora)');
  }

  // por bandeja (categorias de Gmail)
  var cats = [['Principal', 'category:primary'], ['Promociones', 'category:promotions'],
              ['Social', 'category:social'], ['Notificaciones', 'category:updates'],
              ['Foros', 'category:forums']];
  var porBandeja = [];
  cats.forEach(function (c) {
    var n = contar_('after:' + epoch + ' ' + c[1]);
    if (n > 0) porBandeja.push([c[0], n]);
  });
  if (porBandeja.length) {
    L.push('');
    L.push(porBandeja.map(function (x) { return (ICONO_BANDEJA[x[0]] || '📁') + ' ' + x[0] + ' ' + x[1]; }).join('\n'));
  }

  // quien mas escribio
  var porRem = {}, emailDe = {};
  msgs.forEach(function (m) {
    var de = limpiarRemitente_(m.getFrom());
    porRem[de] = (porRem[de] || 0) + 1;
    emailDe[de] = correoDe_(m.getFrom());
  });
  var top = Object.keys(porRem).sort(function (a, b) { return porRem[b] - porRem[a]; }).slice(0, 5);
  if (top.length) {
    L.push('');
    L.push('🏆 QUIÉN MÁS ESCRIBIÓ');
    top.forEach(function (k, i) { L.push(MEDALLA[i] + ' ' + porRem[k] + ' · ' + k.substring(0, 34)); });
  }

  // tendencia de N dias (bloques de 24 h hacia atras)
  var serie = [];
  if (CON_GRAFICAS) {
    try {
      var fin = Date.now();
      for (var i = DIAS_TENDENCIA - 1; i >= 0; i--) {
        var a = fin - (i + 1) * 86400000, b = fin - i * 86400000;
        serie.push([f(new Date(b), 'dd/MM'),
                    contar_('after:' + Math.floor(a / 1000) + ' before:' + Math.floor(b / 1000))]);
      }
      var suma = function (arr) { return arr.reduce(function (s, x) { return s + x[1]; }, 0); };
      var prom30 = suma(serie) / serie.length, prom7 = suma(serie.slice(-7)) / 7;
      var pico = serie.slice().sort(function (x, y) { return y[1] - x[1]; })[0];
      L.push('');
      L.push('📈 TENDENCIA (' + DIAS_TENDENCIA + ' días, conversaciones)');
      L.push(spark_(serie.map(function (x) { return x[1]; })));
      L.push((prom7 >= prom30 ? '⬆️' : '⬇️') + ' Ritmo: ' + prom7.toFixed(1).replace('.', ',') + '/día en 7 días vs ' +
             prom30.toFixed(1).replace('.', ',') + '/día en ' + DIAS_TENDENCIA +
             (prom30 ? ' (' + (prom7 >= prom30 ? '+' : '') + Math.round((prom7 - prom30) * 100 / prom30) + '%)' : ''));
      if (pico && pico[1] > 0) L.push('🔥 Día con más correo: ' + pico[0] + ' (' + pico[1] + ')');
    } catch (e) { serie = []; L.push('📈 (tendencia no disponible: ' + e.message + ')'); }
  }

  // etiqueta que no te puedes perder
  if (ETIQUETA_IMPORTANTE) {
    var et = GmailApp.getUserLabelByName(ETIQUETA_IMPORTANTE);
    L.push('');
    if (!et) {
      L.push('⚠️ ' + ETIQUETA_IMPORTANTE + ': la etiqueta no existe');
    } else {
      var nuevos = [];
      et.getThreads(0, 15).forEach(function (h) {
        h.getMessages().forEach(function (m) {
          if (m.getDate().getTime() >= desde.getTime()) nuevos.push(m);
        });
      });
      if (nuevos.length) {
        L.push('💼 ' + ETIQUETA_IMPORTANTE.toUpperCase() + ' (' + nuevos.length + ' nuevos) ❗');
        nuevos.slice(0, 6).forEach(function (m) {
          L.push('▫️ ' + (m.getSubject() || '(sin asunto)').substring(0, 60) +
                 ' — ' + limpiarRemitente_(m.getFrom()).substring(0, 24));
        });
      } else {
        L.push('💼 ' + ETIQUETA_IMPORTANTE + ': nada nuevo ✅');
      }
    }
  }

  // limpieza posible
  try {
    var viejas = Gmail.Users.Messages.list('me', { q: 'category:promotions older_than:1y', maxResults: 1 }).resultSizeEstimate;
    if (viejas) {
      L.push('');
      L.push('🧹 LIMPIEZA POSIBLE');
      L.push('🗑️ ~' + miles_(viejas) + ' promociones de más de 1 año');
    }
  } catch (e) { /* sin esta seccion no pasa nada */ }

  // graficas (fondo oscuro; tortas salvo la tendencia, que necesita el eje del tiempo)
  if (CON_GRAFICAS) {
    try {
      if (porBandeja.length) {
        graficos.push({ blob: dona_('Correos nuevos por bandeja', porBandeja, 'bandejas.png'),
                        pie: '📊 Correos nuevos por bandeja\n' + leyenda_(porBandeja) });
      }
      if (msgs.length) {
        var estadoLectura = [['Sin leer', sinLeerNuevos], ['Leidos', msgs.length - sinLeerNuevos]]
          .filter(function (r) { return r[1] > 0; });
        graficos.push({ blob: dona_('Leidos y sin leer (nuevos)', estadoLectura, 'lectura.png'),
                        pie: '👁️ Leídos y sin leer\n' + leyenda_(estadoLectura) });
      }
      if (top.length) {
        var filasRem = top.map(function (k) { return [k.substring(0, 24), porRem[k]]; });
        var resto = msgs.length - top.reduce(function (sum, k) { return sum + porRem[k]; }, 0);
        if (resto > 0) filasRem.push(['Otros', resto]);
        graficos.push({ blob: dona_('Quien mas escribio', filasRem, 'remitentes.png'),
                        pie: '🏆 Quién más escribió\n' + leyenda_(filasRem) });
      }
      if (serie.length) {
        graficos.push({ blob: area_('Conversaciones por dia (ultimos ' + DIAS_TENDENCIA + ' dias)', serie, 'tendencia.png'),
                        pie: 'Tendencia de ' + DIAS_TENDENCIA + ' dias' });
      }
    } catch (e) { L.push('⚠️ (gráficas no disponibles: ' + e.message + ')'); Logger.log('Graficas: ' + e.message); }
  }

  var botones = [];
  if (BOTONES_BORRADO) {
    var cache = CacheService.getScriptCache();
    top.forEach(function (k) {
      var correo = emailDe[k];
      if (!correo || correo === Session.getEffectiveUser().getEmail().toLowerCase()) return;
      var clave = Utilities.getUuid().replace(/-/g, '').substring(0, 8);
      cache.put('del_' + clave, correo, 21600);      // 6 horas
      botones.push([{ text: '🗑️ Papelera: ' + k.substring(0, 22) + ' (' + porRem[k] + ')', callback_data: 'd|' + clave }]);
    });
  }
  return { texto: L.join('\n').substring(0, 4000), graficos: graficos, botones: botones };
}

// ---- GRAFICAS (servicio Charts de Google, tema oscuro) -------------------
var TEMA = {
  fondo: '#0f172a', texto: '#e6edf6', suave: '#94a3b8', rejilla: '#334155',
  paleta: ['#38bdf8', '#a78bfa', '#f472b6', '#fbbf24', '#5eead4', '#fb7185', '#4ade80', '#fb923c']
};

function estilo_(tam, color, negrita) {
  return Charts.newTextStyle().setFontSize(tam).setColor(color).setBold(!!negrita).build();
}
/** Aplica un ajuste de estilo; si el servicio no lo acepta, lo registra y sigue con los demas. */
function aplicar_(nombre, fn) {
  try { fn(); } catch (e) { Logger.log('Estilo ignorado (' + nombre + '): ' + e.message); }
}
/** Opcion avanzada (clave tipo Google Charts). */
function opt_(b, clave, valor) {
  aplicar_(clave, function () { b.setOption(clave, valor); });
}
/** Texto claro sobre fondo oscuro: se pide por dos vias (metodo y opcion) para que no quede negro. */
function textoClaro_(b, conEjes) {
  aplicar_('titulo', function () { b.setTitleTextStyle(estilo_(18, TEMA.texto, true)); });
  aplicar_('leyenda', function () { b.setLegendTextStyle(estilo_(14, TEMA.texto)); });
  opt_(b, 'titleTextStyle.color', TEMA.texto);
  opt_(b, 'titleTextStyle.fontSize', 18);
  opt_(b, 'legend.textStyle.color', TEMA.texto);
  opt_(b, 'legend.textStyle.fontSize', 14);
  if (conEjes) {
    aplicar_('ejeX', function () { b.setXAxisTextStyle(estilo_(11, TEMA.suave)); });
    aplicar_('ejeY', function () { b.setYAxisTextStyle(estilo_(11, TEMA.suave)); });
    opt_(b, 'hAxis.textStyle.color', TEMA.suave);
    opt_(b, 'vAxis.textStyle.color', TEMA.suave);
    opt_(b, 'vAxis.gridlines.color', TEMA.rejilla);
    opt_(b, 'hAxis.showTextEvery', 5);
    opt_(b, 'areaOpacity', 0.4);
  }
}

/** Clave de colores en texto: un cuadro de color por trozo, con valor y porcentaje. */
function leyenda_(filas) {
  var total = filas.reduce(function (sum, r) { return sum + r[1]; }, 0) || 1;
  return filas.map(function (r, i) {
    return CUADRO_DONA[i] + ' ' + r[0] + '  ' + r[1] + ' (' + Math.round(r[1] * 100 / total) + '%)';
  }).join('\n');
}

/** Torta tipo dona con fondo oscuro. La clave de colores va en el pie de la foto (ver leyenda_). */
function dona_(titulo, filas, nombre) {
  var dt = Charts.newDataTable()
    .addColumn(Charts.ColumnType.STRING, 'x')
    .addColumn(Charts.ColumnType.NUMBER, 'n');
  filas.forEach(function (r) { dt.addRow([r[0], r[1]]); });
  var b = Charts.newPieChart().setDataTable(dt.build()).setTitle(titulo)
    .setDimensions(800, 460).setBackgroundColor(TEMA.fondo)
    .setColors(PALETA_DONA.slice(0, filas.length));
  aplicar_('sin leyenda', function () { b.setLegendPosition(Charts.Position.NONE); });
  aplicar_('titulo', function () { b.setTitleTextStyle(estilo_(18, TEMA.texto, true)); });
  opt_(b, 'titleTextStyle.color', TEMA.texto);
  opt_(b, 'titleTextStyle.fontSize', 18);
  opt_(b, 'legend', 'none');
  opt_(b, 'pieHole', 0.45);
  opt_(b, 'pieSliceBorderColor', TEMA.fondo);
  opt_(b, 'pieSliceText', 'percentage');
  opt_(b, 'pieSliceTextStyle.color', '#0f172a');
  opt_(b, 'pieSliceTextStyle.fontSize', 16);
  opt_(b, 'backgroundColor', TEMA.fondo);
  return b.build().getAs('image/png').setName(nombre);
}

/** Area para la tendencia en el tiempo. filas = [[fecha, valor], ...] */
function area_(titulo, filas, nombre) {
  var dt = Charts.newDataTable()
    .addColumn(Charts.ColumnType.STRING, 'x')
    .addColumn(Charts.ColumnType.NUMBER, 'n');
  filas.forEach(function (r) { dt.addRow([String(r[0]), r[1]]); });
  var b = Charts.newAreaChart().setDataTable(dt.build()).setTitle(titulo)
    .setDimensions(800, 460).setBackgroundColor(TEMA.fondo)
    .setColors([TEMA.paleta[0]]);
  aplicar_('sin leyenda', function () { b.setLegendPosition(Charts.Position.NONE); });
  textoClaro_(b, true);
  opt_(b, 'backgroundColor', TEMA.fondo);
  return b.build().getAs('image/png').setName(nombre);
}

// ---- UTILIDADES ----------------------------------------------------------
function contar_(consulta) {
  var n = 0, ini = 0, paso = 100, hilos;
  do {
    hilos = GmailApp.search(consulta, ini, paso);
    n += hilos.length;
    ini += paso;
  } while (hilos.length === paso && ini < 500);
  return n;
}

function limpiarRemitente_(de) {
  var m = String(de).match(/^\s*"?([^"<]*?)"?\s*<.*>\s*$/);
  return (m && m[1].trim()) ? m[1].trim() : String(de).replace(/[<>]/g, '').trim();
}

/** Mini grafica de barras con caracteres: ▁▂▃▄▅▆▇█ */
function spark_(valores) {
  var barras = '▁▂▃▄▅▆▇█', max = Math.max.apply(null, valores) || 1;
  return valores.map(function (v) { return barras.charAt(Math.min(7, Math.round(v * 7 / max))); }).join('');
}

function miles_(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
function pct_(a, b) { return b ? (a * 100 / b).toFixed(1).replace('.', ',') : '0'; }

// ---- TELEGRAM ------------------------------------------------------------
function credenciales_() {
  var p = PropertiesService.getScriptProperties();
  var token = p.getProperty('TELEGRAM_TOKEN');
  var chat = p.getProperty('TELEGRAM_CHAT');
  if (!token || !chat) {
    throw new Error('Faltan TELEGRAM_TOKEN y TELEGRAM_CHAT en Configuracion del proyecto > Propiedades de la secuencia de comandos.');
  }
  return { token: token, chat: chat };
}

function telegram_(metodo, payload) {
  var c = credenciales_();
  payload.chat_id = c.chat;
  var r = UrlFetchApp.fetch('https://api.telegram.org/bot' + c.token + '/' + metodo, {
    method: 'post', payload: payload, muteHttpExceptions: true
  });
  if (r.getResponseCode() !== 200) {
    throw new Error('Telegram (' + metodo + ') respondio ' + r.getResponseCode() + ': ' + r.getContentText());
  }
}

/** Envia el texto y luego cada grafica como foto. Una grafica que falle no impide las demas. */
function enviarTodo_(res) {
  var cuerpo = { text: res.texto };
  if (res.botones && res.botones.length) cuerpo.reply_markup = JSON.stringify({ inline_keyboard: res.botones });
  telegram_('sendMessage', cuerpo);
  res.graficos.forEach(function (g) {
    try {
      telegram_('sendPhoto', { photo: g.blob, caption: g.pie });
    } catch (e) {
      Logger.log('No se pudo enviar la grafica "' + g.pie + '": ' + e.message);
    }
  });
}

// ---- BOTONES PARA MOVER A LA PAPELERA ------------------------------------
// Como funciona: bajo el resumen aparecen botones "🗑️ Papelera: <remitente>". Al pulsar uno, el bot
// pregunta si estas seguro (con el numero de conversaciones). Solo al confirmar las mueve a la
// PAPELERA de Gmail (se recuperan 30 dias). Nunca borra de forma definitiva, no toca los
// correos con estrella ni los de la etiqueta ETIQUETA_IMPORTANTE, y solo obedece a TELEGRAM_CHAT.
// Para que el bot "escuche" los botones hay que ejecutar activarBotones() una vez (revisa Telegram
// cada minuto). Importante: usa un bot que NO sea el del dashboard web, porque este lee sus mensajes.

function activarBotones() {
  desactivarBotones();
  ScriptApp.newTrigger('revisarBotones').timeBased().everyMinutes(1).create();
  Logger.log('Botones activos: el bot revisa Telegram cada minuto.');
}
function desactivarBotones() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'revisarBotones') ScriptApp.deleteTrigger(t);
  });
}

function tgRaw_(metodo, payload) {
  var c = credenciales_();
  var r = UrlFetchApp.fetch('https://api.telegram.org/bot' + c.token + '/' + metodo, {
    method: 'post', payload: payload || {}, muteHttpExceptions: true
  });
  var cuerpo = {};
  try { cuerpo = JSON.parse(r.getContentText()); } catch (e) {}
  if (r.getResponseCode() !== 200 || !cuerpo.ok) throw new Error('Telegram (' + metodo + ') ' + r.getResponseCode());
  return cuerpo.result;
}

/** getUpdates por GET con los parametros en la URL (asi el offset siempre se aplica). */
function tgActualizaciones_(offset) {
  var c = credenciales_();
  var url = 'https://api.telegram.org/bot' + c.token + '/getUpdates?offset=' + encodeURIComponent(offset) +
            '&timeout=0&allowed_updates=' + encodeURIComponent(JSON.stringify(['callback_query', 'message']));
  var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  var cuerpo = {};
  try { cuerpo = JSON.parse(r.getContentText()); } catch (e) {}
  if (r.getResponseCode() !== 200 || !cuerpo.ok) throw new Error('getUpdates ' + r.getResponseCode() + ' ' + (cuerpo.description || ''));
  return cuerpo.result;
}

/** Ejecutalo a mano justo despues de pulsar un boton: te manda a Telegram lo que encontro y proceso. */
function probarBotones() { revisarBotones(true); }

function revisarBotones(evento) {
  // Los activadores de Google pasan un objeto de evento como primer argumento: solo `true` activa el informe
  var informe = (evento === true);
  // evita que dos revisiones se pisen (generar el resumen tarda unos segundos)
  var lock = LockService.getScriptLock();
  var R = { lock: true, recibidos: 0, botones: 0, offsetAntes: 0, offsetDespues: 0, procesados: 0, saltados: 0, errores: [], detalle: [] };
  if (!lock.tryLock(1000)) {
    Logger.log('revisarBotones: candado ocupado; salgo.');
    if (informe) tgRaw_('sendMessage', { chat_id: credenciales_().chat, text: '🔧 Otra revisión está en curso (candado ocupado). Espera 1 minuto y repite.' });
    return;
  }
  try {
    var props = PropertiesService.getScriptProperties();
    var offset = parseInt(props.getProperty('TG_OFFSET') || '0', 10);
    R.offsetAntes = offset;
    var ups = tgActualizaciones_(offset);
    R.recibidos = ups.length;
    R.botones = ups.filter(function (u) { return u.callback_query; }).length;
    Logger.log('revisarBotones: ' + ups.length + ' update(s) desde offset ' + offset + ' (botones: ' + R.botones + ')');
    ups.forEach(function (up) { offset = Math.max(offset, up.update_id + 1); });
    props.setProperty('TG_OFFSET', String(offset));       // se guarda ANTES de procesar: nada se repite
    R.offsetDespues = offset;
    var vistos = CacheService.getScriptCache();
    ups.forEach(function (up) {
      var tipo = up.callback_query ? 'boton ' + up.callback_query.data : 'mensaje ' + (up.message && up.message.text);
      if (vistos.get('upd_' + up.update_id)) { R.saltados++; R.detalle.push('↪️ ' + up.update_id + ' ya procesado (' + tipo + ')'); return; }
      vistos.put('upd_' + up.update_id, '1', 21600);
      try {
        Logger.log('procesando update ' + up.update_id + ' (' + tipo + ')');
        R.detalle.push('▶️ ' + up.update_id + ' ' + tipo);
        if (up.callback_query) alPulsar_(up.callback_query);
        else if (up.message) alEscribir_(up.message);
        R.procesados++;
      } catch (e) {
        R.errores.push(e.message);
        Logger.log('Telegram: ' + e.message);
        try { tgRaw_('sendMessage', { chat_id: credenciales_().chat, text: '⚠️ No pude procesar eso: ' + e.message }); } catch (x) {}
      }
    });
  } finally { lock.releaseLock(); }

  if (informe) {
    var t = ['🔧 INFORME DE BOTONES',
             'Mensajes recibidos de Telegram: ' + R.recibidos + ' (botones: ' + R.botones + ')',
             'Offset: ' + R.offsetAntes + ' → ' + R.offsetDespues,
             'Procesados: ' + R.procesados + ' | ya procesados (saltados): ' + R.saltados,
             'Errores: ' + (R.errores.length ? R.errores.join(' | ') : 'ninguno')];
    if (R.detalle.length) t.push('', R.detalle.slice(0, 12).join('\n'));
    if (!R.botones) t.push('', '⚠️ No llegó ningún botón. Pulsa un 🗑️ de un resumen nuevo y vuelve a ejecutar probarBotones.');
    tgRaw_('sendMessage', { chat_id: credenciales_().chat, text: t.join('\n').substring(0, 3900) });
  }
}

/** Comandos de texto. Solo los obedece tu chat; cualquier otro se ignora. */
function alEscribir_(m) {
  var c = credenciales_();
  if (String(m.chat && m.chat.id) !== String(c.chat)) return;
  var texto = String(m.text || '').trim();
  var cmd = texto.split(/\s+/)[0].toLowerCase().replace(/@.*$/, '');
  if (cmd === '/estado') {
    var cd = CacheService.getScriptCache();
    if (cd.get('estado_reciente')) return;                  // ya se esta atendiendo / se atendio hace instantes
    cd.put('estado_reciente', '1', 60);
    // /estado = ultimas 24 h;  /estado 6 = ultimas 6 horas;  /estado 3d = ultimos 3 dias
    var arg = (texto.split(/\s+/)[1] || '').toLowerCase();
    var horas = 24;
    if (/^\d+d$/.test(arg)) horas = parseInt(arg, 10) * 24;
    else if (/^\d+h?$/.test(arg)) horas = parseInt(arg, 10);
    horas = Math.max(1, Math.min(horas || 24, 24 * 30));
    tgRaw_('sendMessage', { chat_id: c.chat, text: '⏳ Preparando tu estado (últimas ' + (horas % 24 === 0 && horas >= 48 ? horas / 24 + ' días' : horas + ' h') + ')…' });
    enviarTodo_(construir_(new Date(Date.now() - horas * 3600 * 1000), false));
  } else if (cmd === '/ayuda' || cmd === '/start' || cmd === '/help') {
    tgRaw_('sendMessage', { chat_id: c.chat, text:
      '🤖 Comandos\n/estado → resumen de las últimas 24 h, con gráficas\n/estado 6 → últimas 6 horas\n/estado 3d → últimos 3 días\n' +
      '🗑️ Los botones bajo cada resumen mueven a la papelera, siempre con confirmación.' });
  }
}

/** Muestra los comandos en el menu del bot. Ejecutar una vez. */
function registrarComandos() {
  tgRaw_('setMyCommands', { commands: JSON.stringify([
    { command: 'estado', description: 'Resumen de tu Gmail ahora (ej: /estado 6 o /estado 3d)' },
    { command: 'ayuda', description: 'Ver los comandos' }
  ]) });
  Logger.log('Comandos registrados.');
}

function correoDe_(de) {
  var m = String(de).match(/<([^>]+)>/);
  return (m ? m[1] : String(de)).trim().toLowerCase();
}

function consultaBorrado_(correo) {
  if (!/^[^\s<>"'()]+@[^\s<>"'()]+\.[^\s<>"'()]+$/.test(correo)) throw new Error('Remitente no valido.');
  var q = 'from:' + correo + ' -is:starred';
  if (ETIQUETA_IMPORTANTE) q += ' -label:' + ETIQUETA_IMPORTANTE.toLowerCase().replace(/\s+/g, '-');
  return q;
}

/** Responde al clic del boton. Si Telegram ya lo considera vencido (el bot revisa cada minuto),
 *  da error: no debe cortar el resto del proceso. */
function responder_(payload) {
  try { tgRaw_('answerCallbackQuery', payload); }
  catch (e) { Logger.log('answerCallbackQuery ignorado: ' + e.message); }
}

function alPulsar_(cb) {
  var c = credenciales_();
  var chat = cb.message && cb.message.chat && cb.message.chat.id;
  if (String(chat) !== String(c.chat)) {                 // solo obedece a tu chat
    Logger.log('boton de un chat no autorizado: ' + chat + ' (tu chat es ' + c.chat + ')');
    responder_({ callback_query_id: cb.id, text: 'No autorizado.' });
    return;
  }
  var partes = String(cb.data || '').split('|');
  var accion = partes[0], clave = partes[1];
  var cache = CacheService.getScriptCache();
  var correo = cache.get('del_' + clave);
  Logger.log('boton accion=' + accion + ' clave=' + clave + ' correo=' + correo);
  if (!correo) {
    responder_({ callback_query_id: cb.id, text: 'Este boton expiro.' });
    tgRaw_('sendMessage', { chat_id: c.chat, text: '⌛ Ese botón expiró (duran 6 horas). Escribe /estado para recibir uno nuevo.' });
    return;
  }
  responder_({ callback_query_id: cb.id });
  var q = consultaBorrado_(correo);

  if (accion === 'd') {                                  // 1) pedir confirmacion
    var n = contarHilos_(q);
    if (!n) { tgRaw_('sendMessage', { chat_id: c.chat, text: 'No hay conversaciones de ' + correo + ' para mover (o tienen estrella).' }); return; }
    tgRaw_('sendMessage', {
      chat_id: c.chat,
      text: '⚠️ ¿Mover a la papelera ' + (n >= TOPE_HILOS_BORRADO ? 'más de ' : '') + n + ' conversaciones de\n' + correo +
            '?\nSe recuperan durante 30 días. No toca las que tienen estrella.',
      reply_markup: JSON.stringify({ inline_keyboard: [[
        { text: '✅ Sí, a la papelera', callback_data: 'y|' + clave },
        { text: '❌ Cancelar', callback_data: 'n|' + clave }
      ]] })
    });
  } else if (accion === 'y') {                           // 2) confirmado
    cache.remove('del_' + clave);                        // evita repetirlo con un segundo toque
    var movidos = moverAPapelera_(q);
    tgRaw_('sendMessage', { chat_id: c.chat, text: '🗑️ Listo: ' + movidos + ' conversaciones de ' + correo +
                                                  ' están en la papelera de Gmail (se recuperan 30 días).' });
  } else if (accion === 'n') {
    cache.remove('del_' + clave);
    tgRaw_('sendMessage', { chat_id: c.chat, text: '❌ Cancelado. No se movió nada.' });
  }
}

function contarHilos_(q) {
  var n = 0, ini = 0, hilos;
  do { hilos = GmailApp.search(q, ini, 100); n += hilos.length; ini += 100; }
  while (hilos.length === 100 && n < TOPE_HILOS_BORRADO);
  return n;
}

function moverAPapelera_(q) {
  var total = 0, hilos;
  do {
    hilos = GmailApp.search(q, 0, 100);                  // siempre desde 0: lo movido sale de la busqueda
    if (hilos.length) { GmailApp.moveThreadsToTrash(hilos); total += hilos.length; }
  } while (hilos.length && total < TOPE_HILOS_BORRADO);
  return total;
}

/** Ejecutalo a mano si los botones no responden: revisa cada pieza y te manda el resultado a Telegram. */
function diagnosticoBotones() {
  var c = credenciales_();
  var props = PropertiesService.getScriptProperties();
  var L = ['🔧 DIAGNÓSTICO DE BOTONES'];
  var trig = ScriptApp.getProjectTriggers().map(function (t) { return t.getHandlerFunction(); });
  var nBot = trig.filter(function (x) { return x === 'revisarBotones'; }).length;
  var nRes = trig.filter(function (x) { return x === 'resumen'; }).length;
  L.push((nBot === 1 ? '✅' : '❌') + ' Activador revisarBotones: ' + nBot + ' (debe ser 1)');
  L.push((nRes === 2 ? '✅' : '⚠️') + ' Activadores resumen: ' + nRes + ' (deben ser 2)');
  L.push('ℹ️ TELEGRAM_CHAT = ' + c.chat);
  L.push('ℹ️ Botones activados en el codigo: ' + (BOTONES_BORRADO ? 'si' : 'NO (BOTONES_BORRADO=false)'));
  try {
    var w = tgRaw_('getWebhookInfo');
    L.push((w.url ? '❌ Hay un webhook activo (bloquea los botones): ' + w.url : '✅ Sin webhook'));
  } catch (e) { L.push('⚠️ getWebhookInfo: ' + e.message); }
  try {
    var off = parseInt(props.getProperty('TG_OFFSET') || '0', 10);
    var pend = tgActualizaciones_(off);
    var cb = pend.filter(function (u) { return u.callback_query; }).length;
    L.push('ℹ️ Pendientes de procesar: ' + pend.length + ' (botones: ' + cb + ')');
  } catch (e) { L.push('❌ getUpdates: ' + e.message); }
  try {
    var ejemplo = GmailApp.search('in:inbox', 0, 1).length;
    L.push('✅ Gmail responde (' + ejemplo + ' resultado de prueba)');
  } catch (e) { L.push('❌ Gmail: ' + e.message + ' (¿falta autorizar?)'); }
  L.push('');
  L.push('Ahora pulsa un botón 🗑️ de un resumen NUEVO (/estado) y espera 1-2 min. Si hay un error te llegará aquí como «⚠️ No pude procesar eso».');
  tgRaw_('sendMessage', { chat_id: c.chat, text: L.join('\n') });
  Logger.log(L.join('\n'));
}
