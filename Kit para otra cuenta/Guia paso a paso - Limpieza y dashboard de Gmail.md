# Guía paso a paso: analizar, organizar y limpiar un Gmail con un dashboard propio

Esta guía describe todo lo que se hizo con la cuenta original (36.063 correos, 3,5 GB, 85,7 % sin leer) para que se pueda repetir en **otra cuenta de Gmail**. Está ordenada en el orden real en que se hizo.

**Incluye la actualización periódica de los datos (sección 9).**

**Resultado esperado:** un dashboard local con tarjetas, filtros y gráficos; el correo repetitivo ordenado en etiquetas con reglas automáticas; lo inútil en la papelera; y lo importante (por ejemplo, ofertas de trabajo) protegido.

> **Privacidad.** Todo corre en tu computador. El script solo habla con la API de Google. En el análisis se leen cabeceras (remitente, asunto, fecha, tamaño, etiquetas), no el cuerpo de los correos. La única excepción es `buscar_empleo.py`, que usa el buscador de Gmail.

---

## 0. Qué necesitas antes de empezar

| Requisito | Detalle |
|---|---|
| Computador | Windows, Mac o Linux con Python 3.8 o superior |
| Cuenta | La cuenta de Gmail a analizar (la llamaremos *la cuenta nueva*) |
| Tiempo | Unos 15 minutos de configuración, más 15 a 60 minutos de descarga (se hace sola) |
| Navegador | Chrome, para autorizar el acceso |

Instala las librerías de Google (una sola vez):

```powershell
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

---

## 1. Preparar la carpeta del kit

1. Crea una carpeta nueva, por ejemplo `Dashboard Gmail - cuenta2`.
2. Copia dentro estos archivos del kit original (están en `Kit para otra cuenta\`):

| Archivo | Para qué sirve |
|---|---|
| `analizar_gmail.py` | Descarga los metadatos y genera los datos del dashboard |
| `dashboard.html` | El dashboard (se abre con doble clic) |
| `chart.umd.min.js` | Librería de gráficos, funciona sin internet |
| `sincronizar.py` | Pone al día la caché después de borrar o mover correos |
| `organizar_correos.py` | Crea etiquetas y reglas, mueve y borra por remitente |
| `etiquetas.json` | Lista `carpeta → remitente`. **Se edita para cada cuenta** |
| `crear_regla.py` | Crea o elimina reglas sueltas |
| `buscar_empleo.py` | Detecta correos de procesos de selección reales |
| `vigilar.py` | Completa la descarga solo y avisa al terminar (opcional) |
| `actualizar_dashboard.bat` | Doble clic: actualiza los datos y abre el dashboard |
| `resumen_telegram.py` | Envía por Telegram un resumen del buzón y lo nuevo |
| `programar_resumen_telegram.bat` | Programa ese resumen a las 19:00 y 21:00 en Windows |
| `ejecutar_resumen.bat` | Lo que ejecutan las tareas programadas (sincroniza y envía) |
| `nube\Codigo.gs` y `nube\appsscript.json` | El mismo resumen, con gráficas, ejecutado en Google (no necesita el PC) |
| `docs\` | Versión publicable en GitHub Pages: cada persona conecta su cuenta y ve su análisis (sección 14) |
| `Apps Script web\` | Versión como aplicación web de Apps Script, con alertas por persona y borrado opcional (sección 15) |

3. **No copies** estos archivos de la cuenta original, porque pertenecen a ella: `client_secret.json`, `token*.json`, `cache_gmail.db`, `datos_gmail.js`.

---

## 2. Crear las credenciales de Google (una vez por cuenta, ~5 minutos)

Google exige que cada programa que lee un Gmail tenga sus credenciales. Se pueden usar las de otro proyecto, pero lo simple y limpio es crear un proyecto nuevo.

1. **Crear el proyecto.** Entra a <https://console.cloud.google.com/projectcreate>, con la cuenta nueva. Nombre: `Dashboard Gmail` → **Crear**.
2. **Activar la API de Gmail.** <https://console.cloud.google.com/apis/library/gmail.googleapis.com> → **Habilitar**.
3. **Pantalla de consentimiento.** <https://console.cloud.google.com/apis/credentials/consent>
   - Tipo de usuario: **Externo** → Crear.
   - Nombre de la app: `Dashboard Gmail`. Correo de asistencia y de contacto: el de la cuenta nueva.
   - Guardar y continuar (deja los permisos como están).
   - En **Usuarios de prueba** (o *Público*, según la versión del panel) agrega **la cuenta nueva**. Sin esto, Google bloquea el acceso.
4. **Crear la credencial.** <https://console.cloud.google.com/apis/credentials> → **Crear credenciales** → **ID de cliente de OAuth**.
   - Tipo de aplicación: **App de escritorio** (no *Aplicación web*, que pide una URL de redirección).
   - Nombre: `Dashboard Gmail PC` → **Crear** → **Descargar JSON**.
5. Renombra el archivo descargado a `client_secret.json` y déjalo en la carpeta del kit.

> **Cuidado.** `client_secret.json` y los `token*.json` dan acceso a ese Gmail. No los compartas, no los subas a ningún sitio y no los dejes en una carpeta compartida.

---

## 3. Descargar el buzón y ver el dashboard

Abre PowerShell en la carpeta del kit y ejecuta:

```powershell
python analizar_gmail.py
```

1. Se abre el navegador. Elige la cuenta nueva. Google dirá **«Google no ha verificado esta aplicación»**: es normal, la app es tuya. Pulsa *Configuración avanzada → Ir a Dashboard Gmail (no seguro)* y acepta.
2. Vuelve a la ventana negra. Verás una barra de progreso.
3. Al terminar se abre el dashboard. Si se corta, vuelve a ejecutar el mismo comando: **retoma donde quedó**.

**Velocidad y cuota.** El script usa por defecto lotes de 40 correos y 1 segundo de pausa, que es seguro. Con 36.000 correos tarda de 45 a 60 minutos. Se puede acelerar con `--lote 100 --pausa 0.4`, pero **no es recomendable**: en la cuenta original eso superó la cuota por segundo de Google, los bloques fallaron en silencio y la descarga terminó con 7.826 de 36.047 correos. El script actual ya reintenta los lotes fallidos y baja el ritmo solo.

**Si Google responde 502 Bad Gateway** en todos los lotes, el script cambia a pedir los correos uno por uno. Es más lento pero no pierde ninguno. Para dejarlo trabajando solo y que avise al terminar, usa `python vigilar.py`.

Comandos útiles:

| Comando | Qué hace |
|---|---|
| `python analizar_gmail.py --resumen` | Regenera el dashboard desde la caché, sin descargar |
| `python analizar_gmail.py --tope 500` | Prueba rápida con 500 correos |
| `python analizar_gmail.py --spam` | Incluye spam y papelera |
| `python analizar_gmail.py --reiniciar` | Borra la caché y empieza de cero |

---

## 4. Leer el dashboard para decidir qué limpiar

El dashboard tiene seis pestañas y una barra de filtros (texto, dominio, categoría, año desde/hasta, **mes**, tamaño, etiqueta, sin leer, boletín).

| Pestaña | Qué responde |
|---|---|
| **Resumen** | Frases automáticas, volumen por año, reparto por categoría, tortas de leído/no leído, dominios y tamaño |
| **Bandejas de Gmail** | Principal, Promociones, Social y Notificaciones: tarjetas, tortas, historia mensual y anual, y el detalle de cada bandeja con sus remitentes |
| **Remitentes** | Quién escribe más, quién ocupa más espacio, dominios agrupados. El botón *Regla* copia `from:direccion` |
| **Tendencias** | Evolución mensual, acumulado histórico, estacionalidad por mes, día de la semana, mapa de calor día × hora, peso y antigüedad de lo no leído |
| **Etiquetas** | Etiquetas por volumen, reparto, espacio y evolución por año |
| **Plan de limpieza** | Reglas con cuántos correos y cuánto espacio libera cada una, y los remitentes que casi nunca abriste |

**Cómo decidir.** Anota los 10 remitentes que más correo mandan con 90 % o más sin abrir. En la cuenta original eso fueron alertas de empleo, newsletters, bancos y tiendas: 13.957 correos y unos 1,3 GB. Esa lista es la que se carga en el paso 5.

---

## 5. Organizar: etiquetas y reglas por remitente

`organizar_correos.py` hace dos cosas por cada remitente de `etiquetas.json`: crea una etiqueta y una regla (para que lo nuevo se etiquete solo y no pase por la bandeja), y mueve el correo que ya existe.

### 5.1 Editar `etiquetas.json`

Cada entrada es un par `carpeta` y `remitente`. El remitente puede ser una dirección completa o un **dominio**. Usa dominio cuando el remitente rota de dirección: Trabajando.com usaba más de 60 direcciones (`norespondercl.01@…`, `.02@…`), así que una regla por dirección era imposible.

```json
[
  { "carpeta": "LinkedIn Empleo",    "remitente": "jobalerts-noreply@linkedin.com" },
  { "carpeta": "Portales de empleo", "remitente": "computrabajo.com" },
  { "carpeta": "Portales de empleo", "remitente": "indeed.com" },
  { "carpeta": "GitHub",             "remitente": "github.com" }
]
```

- Para juntar varios remitentes en **una sola etiqueta**, repite el mismo nombre de `carpeta`. La etiqueta se crea una vez y cada remitente agrega su regla.
- Verifica la dirección real antes de escribirla. En la cuenta original, «Tempo» era en realidad `paratodos@tenpo.cl` y la primera simulación dio cero correos.

### 5.2 Probar, simular, aplicar

```powershell
python organizar_correos.py --local      # solo cuenta desde la caché, no se conecta
python organizar_correos.py --simular    # consulta Gmail, no cambia nada
python organizar_correos.py --aplicar    # crea etiquetas y reglas, y mueve el correo
```

La primera vez pide **dos permisos** (modificar correos y crear reglas) y guarda `token_organizar.json`. Verifica que la simulación coincida con la cifra de `--local`: en la cuenta original ambas dieron 13.138.

Archivar y etiquetar **no libera espacio**. Solo saca el correo de la bandeja. El espacio se recupera borrando.

### 5.3 Deshacer

- Una regla: `python crear_regla.py --listar` para ver el id, luego `python crear_regla.py --eliminar ID`.
- Una etiqueta: en Gmail, clic derecho sobre la etiqueta → *Eliminar*. El correo no se borra.
- Devolver a la bandeja: abre la etiqueta, selecciona todo y *Mover a la bandeja de entrada*.

---

## 6. Proteger lo importante antes de borrar

Antes de borrar, identifica el correo que **no se puede perder** y etiquétalo. En la cuenta original fueron las ofertas y entrevistas de trabajo.

```powershell
python buscar_empleo.py --listar                                      # solo muestra
python buscar_empleo.py --listar --csv ofertas.csv                    # y exporta la lista
python buscar_empleo.py --etiquetar "Ofertas y entrevistas" --aplicar
```

Este script lee el texto completo vía el buscador de Gmail, descarta portales y boletines, y **solo pone la etiqueta** (no archiva). Encontró 119 correos de unas 23 empresas. Busca por palabras, así que revisa la lista y quita a mano lo que sobre.

Si tu caso de protección no es de empleo, crea la etiqueta a mano en Gmail y aplícala a esos correos antes de seguir.

---

## 7. Borrar

Hay tres niveles, de menos a más definitivo:

| Nivel | Comando | Libera espacio | Se puede deshacer |
|---|---|---|---|
| Archivar / etiquetar | `--aplicar` | No | Sí |
| Papelera | `--aplicar --borrar` | No, hasta vaciarla (se purga sola a los 30 días) | Sí, durante 30 días |
| Definitivo | `--aplicar --definitivo --si` | Sí, al instante | **No** |

Con una etiqueta de protección, pasa su nombre en `--proteger` para que nada que la tenga se borre aunque coincida con otro remitente:

```powershell
python organizar_correos.py --aplicar --borrar --proteger "Ofertas y entrevistas"
```

El orden que se siguió en la cuenta original, y que conviene repetir:

1. Contar la intersección entre lo que se va a borrar y lo protegido. En la cuenta original fue 0, verificado por dos vías.
2. Borrar a la **papelera**, no definitivo.
3. Revisar la papelera unos días.
4. **Vaciar la papelera** desde Gmail. Ahí se recupera el espacio (≈ 1,3 GB en la cuenta original).

---

## 8. Reglas para el correo nuevo y cómo mantenerlo

Las reglas creadas en el paso 5 ya etiquetan y archivan lo que llegue. Para una regla suelta:

```powershell
python crear_regla.py --etiqueta "GitHub" --desde github.com --saltar-bandeja
python crear_regla.py --listar
```

- La regla filtra por dominio (`github.com`) y cubre `notifications@`, `noreply@` y cualquier otra dirección futura.
- Si un servicio manda cosas que sí requieren tu acción (por ejemplo avisos de CI fallido), mejor **no archives**: usa solo etiqueta, o quita `--saltar-bandeja`.
- Las reglas de Gmail solo afectan al correo **nuevo**. Lo antiguo se mueve con `organizar_correos.py`.

Después de cualquier cambio en Gmail, actualiza el dashboard (sección 9).

---

## 9. Actualizar la data del dashboard

El dashboard muestra una **foto** del buzón guardada en `cache_gmail.db` y `datos_gmail.js`. No se actualiza solo: hay que refrescar la foto cuando llegan correos nuevos o cuando borras, mueves o lees correos.

### 9.1 La forma rápida (recomendada)

Haz **doble clic en `actualizar_dashboard.bat`**. Ejecuta `python sincronizar.py` y abre el dashboard al terminar. Con un buzón de 16.000 correos tarda unos minutos (la primera vez, algo más). Se puede dejar corriendo mientras haces otra cosa.

Lo mismo, a mano:

```powershell
cd "RUTA\A\LA\CARPETA\DEL\KIT"
python sincronizar.py
```

Qué hace `sincronizar.py`, sin volver a descargar todo el buzón:

1. Lee qué correos existen hoy en Gmail (sin contar papelera ni spam).
2. Reconstruye las etiquetas de cada correo, consultando etiqueta por etiqueta.
3. Actualiza en la caché las etiquetas, la categoría (Principal, Promociones, etc.) y el estado leído/no leído de los que ya estaban.
4. Descarga solo los metadatos de los correos **nuevos**.
5. Quita de la caché los que ya no existen (borrados, en papelera o en spam).
6. Refresca el catálogo de etiquetas y regenera `datos_gmail.js` y `reporte_limpieza.md`.

Después, recarga la pestaña del dashboard (F5, o Ctrl+F5 si sigue mostrando lo anterior).

### 9.2 Cuándo actualizar

| Situación | Qué ejecutar |
|---|---|
| Quieres ver el correo de la última semana | `python sincronizar.py` |
| Acabas de borrar, mover, etiquetar o vaciar la papelera | `python sincronizar.py` |
| Leíste o marcaste correos y quieres ver el % sin leer real | `python sincronizar.py` |
| Cambiaste algo del dashboard o de los scripts y solo quieres regenerar | `python analizar_gmail.py --resumen` (usa la caché, no se conecta) |
| Pasó mucho tiempo (meses) o algo se ve raro | `python sincronizar.py`; si sigue mal, `python analizar_gmail.py --reiniciar` y descargar todo otra vez |

Frecuencia sugerida: una vez al mes para seguimiento, y siempre después de una limpieza. Si solo quieres saber cuánto cambió, usa `python sincronizar.py --simular`: cuenta las diferencias y no modifica la caché.

### 9.3 Diferencia entre los dos comandos

| | `sincronizar.py` | `analizar_gmail.py` |
|---|---|---|
| Se conecta a Gmail | Sí | Sí, salvo con `--resumen` |
| Detecta correos nuevos | Sí | Sí |
| Detecta correos borrados | **Sí** | No |
| Actualiza leído / etiquetas | **Sí** | No (solo en correos nuevos) |
| Sirve para el día a día | **Sí** | Solo para la primera descarga |

Por eso, tras la primera descarga, el comando de uso diario es siempre `sincronizar.py`.

### 9.4 Permisos y caducidad

`sincronizar.py` usa el token `token_organizar.json`, que se crea la primera vez que ejecutas `organizar_correos.py` (paso 5). Si todavía no lo has hecho en esta cuenta, ejecuta primero:

```powershell
python organizar_correos.py --simular
```

Eso abre el navegador, pide los permisos y guarda el token. No cambia nada en tu correo.

Si la app de Google Cloud sigue en modo **Prueba**, el permiso caduca a los 7 días. Cuando ocurra, el `.bat` mostrará un error `invalid_grant`. Se resuelve así:

1. Borra `token_organizar.json`.
2. Ejecuta `python organizar_correos.py --simular` y autoriza de nuevo.
3. Vuelve a ejecutar `actualizar_dashboard.bat`.

Para no repetirlo cada semana, en la pantalla de consentimiento de Google Cloud cambia el estado de la app a **En producción**. Para uso personal no hace falta verificarla: seguirás viendo el aviso de «app no verificada» al autorizar.

### 9.5 Qué no cambia al actualizar

- **Actualizar no borra ni mueve nada en Gmail.** Solo lee el estado del buzón y lo copia a la caché local.
- **Las reglas siguen activas.** Los correos nuevos de remitentes con regla llegan ya etiquetados y archivados, y aparecerán en el dashboard con su etiqueta.
- **Los correos de una cuenta nueva** nunca se mezclan con los de otra: cada carpeta del kit tiene su propia caché.

---

## 10. Problemas que ya ocurrieron y cómo se resolvieron

| Síntoma | Causa | Solución |
|---|---|---|
| La descarga termina con muchos menos correos de los esperados | Lotes demasiado grandes y rápidos superan la cuota por segundo; los lotes fallidos se contaban como descargados | Usar `--lote 40 --pausa 1.0`. El script actual reintenta los lotes fallidos y baja el ritmo |
| Todo da `502 Bad Gateway` a mitad de descarga | El endpoint de lotes de Google cayó | El script pide los correos uno por uno. `vigilar.py` lo deja trabajando solo |
| Tras `sincronizar.py` el dashboard muestra 0 sin leer y sin etiquetas | `messages.list` **no devuelve las etiquetas** (solo id e hilo), así que se guardaban vacías | Corregido: ahora se lista cada etiqueta por separado. Usa la versión nueva de `sincronizar.py` |
| Los gráficos de etiquetas muestran una sola barra enorme | La etiqueta del sistema `IMPORTANT`, que pone Gmail sola, tapa a las demás | Corregido: `analizar_gmail.py` ya ignora `IMPORTANT` y `YELLOW_STAR` |
| «Access blocked» | La cuenta no está como usuario de prueba | Paso 2.3, agregar la cuenta |
| «invalid_grant» o el token dejó de funcionar | Con la app en modo *Prueba*, Google caduca el permiso cada 7 días | Borra el `token*.json` correspondiente y vuelve a ejecutar |
| El dashboard no muestra los correos nuevos | Muestra la foto de la última actualización | Ejecuta `actualizar_dashboard.bat` y recarga con Ctrl+F5 |
| El dashboard abre vacío | Falta `datos_gmail.js` junto a `dashboard.html` | Ejecuta `python analizar_gmail.py --resumen` |
| `FALTA EL ARCHIVO client_secret.json` | Nombre o carpeta incorrectos | Paso 2.5 |
| Un remitente da 0 correos al simular | La dirección está mal escrita | Búscala en la caché o en Gmail y corrígela en `etiquetas.json` |

---

## 11. Alertas por Telegram: aviso al terminar y resumen periódico

Hay dos avisos distintos:

| Aviso | Script | Cuándo llega |
|---|---|---|
| Fin de descarga | `vigilar.py` | Una vez, cuando termina la primera descarga larga |
| **Resumen periódico** | `resumen_telegram.py` | Cada día o cada semana, con el estado del buzón y lo nuevo |

### 11.1 Crear el bot de Telegram (2 minutos, desde el celular)

1. En Telegram busca `@BotFather` y escribe `/newbot`.
2. Elige un nombre (`Avisos Gmail`) y un usuario que termine en `bot` (`avisos_gmail_bot`).
3. BotFather te devuelve un **token**, una línea parecida a `7123456789:AAH8kL2mN9...`. Cópiala.
4. Abre tu bot nuevo y pulsa **Start**, o escríbele «hola». Sin este paso el bot no puede escribirte.

> **Cuidado.** El token es una llave: quien lo tenga puede escribir como tu bot. No lo publiques ni lo pegues en chats públicos.

### 11.2 Configurar `notificar.json`

Copia `notificar.json.ejemplo` a `notificar.json`, borra el bloque `correo` y deja solo `telegram`:

```json
{
  "telegram": {
    "token": "7123456789:AAH8kL2mN9...",
    "chat": "123456789"
  }
}
```

Para conseguir el número de `chat` sin buscarlo a mano, con el token ya puesto ejecuta:

```powershell
python resumen_telegram.py --buscar-chat
```

Imprime tu chat id. Cópialo al campo `chat`.

### 11.3 Probar el resumen

```powershell
python resumen_telegram.py --simular      # muestra el mensaje en pantalla, no envía
python resumen_telegram.py                # lo envía a Telegram
```

El mensaje incluye:

- Estado del buzón: total de correos, espacio y porcentaje sin leer.
- Lo nuevo de los últimos días: cuántos, cuántos sin leer, reparto por bandeja y los 5 remitentes que más escribieron.
- Los correos nuevos de una etiqueta que no te puedes perder (por defecto `Ofertas y entrevistas`, con asunto y remitente).
- Cuánto se podría limpiar: promociones de más de 1 año.

Ejemplo real, de la cuenta original:

```text
Resumen de Gmail - cuenta@gmail.com
19/11/2026 12:26

BUZON
16.264 correos  |  2,0 GB
12.349 sin leer (75,9%)

NUEVOS (ultimos 7 dias)
143 correos, 117 sin leer
Promociones 56 / Notificaciones 48 / Principal 32 / Otros 7

Ofertas y entrevistas: nada nuevo

LIMPIEZA POSIBLE
3.915 promociones de mas de 1 ano (210 MB)
```

Opciones:

| Opción | Qué hace |
|---|---|
| `--sincronizar` | Pone al día la caché con Gmail antes de resumir. Sin esto, el resumen usa la última actualización |
| `--dias 1` | Resumen diario: «nuevos» cuenta solo las últimas 24 horas. Por defecto son 7 |
| `--importante "Etiqueta"` | Destaca los correos nuevos de esa etiqueta. Con `""` se quita |
| `--simular` | Solo muestra el mensaje |

### 11.4 Que llegue solo

Haz doble clic en `programar_resumen_telegram.bat`. Crea dos tareas programadas de Windows, a las **19:00** y a las **21:00**, que ejecutan `ejecutar_resumen.bat`. Ese archivo corre:

```powershell
python -W ignore resumen_telegram.py --sincronizar --dias 1
```

y deja el registro en `resumen_telegram.log`.

- Para cambiar las horas, edita las dos líneas `schtasks` del `.bat` antes de ejecutarlo.
- **El nombre de la tarea no puede llevar `:`** (por eso se llaman `... 1900` y `... 2100`). Con dos puntos Windows responde «El parámetro no es correcto».
- Si `python` no está en el PATH de las tareas, pon la ruta completa de `python.exe` en `ejecutar_resumen.bat`.
- El computador debe estar encendido a esa hora. Si no lo está, ese resumen no llega.
- Para un resumen semanal, cambia `/SC DAILY` por `/SC WEEKLY /D MON` y `--dias 1` por `--dias 7`.
- Para quitar una tarea: `schtasks /Delete /TN "Resumen Gmail Telegram 1900" /F`.
- Como usa `--sincronizar`, depende del token de Google de la sección 9.4. Si caduca, el resumen no se envía hasta renovarlo.
- **No consume tokens de IA.** Es un script de Python que usa la API de Gmail y la de Telegram.

### 11.5 Resumen en la nube (sin depender del PC)

La tarea de Windows (11.4) solo funciona con el computador encendido. La alternativa es ejecutar el resumen en **Google Apps Script**, que corre en los servidores de Google, dentro de tu propia cuenta de Gmail. Está en `Kit para otra cuenta
ube\` (`Codigo.gs` y `appsscript.json`).

| | Windows (11.4) | Nube (11.5) |
|---|---|---|
| Necesita el PC encendido | Sí | **No** |
| Permiso de Google que caduca cada 7 días | Sí | **No** |
| Costo | Gratis | Gratis |
| Tokens de IA | 0 | 0 |
| Contenido del resumen | Texto, desde la caché local | Texto **más 4 gráficas** de fondo oscuro, usando búsquedas de Gmail |

**Qué incluye el mensaje** (cada sección lleva su icono: 📊 buzón, 🆕 nuevos, 🏆 medallas para los remitentes, 📈 tendencia con una mini gráfica de barras ▁▂▃▅▇, 💼 etiqueta importante, 🧹 limpieza; los iconos de cada bandeja y las flechas 🔺🔻 de la comparación también):

- **Buzón:** total de correos y sin leer.
- **Nuevos desde el último resumen** (el de las 19:00 cubre desde las 21:00 del día anterior y el de las 21:00 cubre las 2 horas siguientes), con el porcentaje sin leer y la comparación con el periodo anterior de igual duración.
- **Reparto por bandeja** y los 5 remitentes que más escribieron.
- **Tendencia de 30 días:** ritmo por día en los últimos 7 días frente a los 30, y el día con más correo.
- Los correos nuevos de `Ofertas y entrevistas`, con asunto y remitente.
- Una estimación de las promociones de más de 1 año que se podrían limpiar.

**Y cuatro gráficas de fondo oscuro**, enviadas como fotos justo después del texto: tres tortas (correos nuevos por bandeja, leídos y sin leer, y quién más escribió, con el valor y el porcentaje en la leyenda) y la tendencia de conversaciones por día de los últimos 30 días, que va como área porque una torta no puede mostrar el tiempo. Las dibuja el servicio `Charts` de Google dentro de tu proyecto: no se envía nada a terceros. Para recibir solo el texto, pon `var CON_GRAFICAS = false;` al inicio de `Codigo.gs`. Los colores están en la constante `TEMA` (fondo, texto, rejilla y paleta) por si quieres cambiarlos.

> Las cifras de «periodo anterior» y de la tendencia cuentan **conversaciones** (hilos), porque así busca Gmail. No son idénticas al número de correos individuales, y por eso aparecen con `~`.

**Instalación (10 minutos):**

1. **Regenera el token del bot** (recomendado, sobre todo si estuvo visible en un chat): en Telegram, `@BotFather` → `/revoke` → elige el bot → copia el token nuevo.
2. Entra a <https://script.google.com> con la cuenta de Gmail a resumir → **Proyecto nuevo**. Ponle de nombre `Resumen Gmail`.
3. Borra el contenido de `Codigo.gs` y pega el de `Kit para otra cuenta
ube\Codigo.gs`.
4. En el menú izquierdo, junto a **Servicios**, pulsa **+**, elige **Gmail API** y **Agregar**. El identificador debe quedar como `Gmail`.
5. **Configuración del proyecto** (engranaje) → **Propiedades de la secuencia de comandos** → **Agregar propiedad**:

   | Propiedad | Valor |
   |---|---|
   | `TELEGRAM_TOKEN` | el token del bot |
   | `TELEGRAM_CHAT` | tu chat id (`python resumen_telegram.py --buscar-chat` lo muestra) |

   Mientras estás ahí, confirma que la **zona horaria** sea la tuya (en el proyecto original, `America/Santiago`).
6. Vuelve al editor, elige la función **`probar`** y pulsa **Ejecutar**. La primera vez pide permisos: *Revisar permisos* → tu cuenta → *Configuración avanzada* → *Ir a Resumen Gmail (no seguro)* → *Permitir*. Es tu propio script, por eso Google avisa que no está verificado. Debe llegarte un mensaje con la etiqueta (PRUEBA) a Telegram.
7. Elige la función **`programar`** y **Ejecutar**. Crea los envíos diarios a las 19:00 y a las 21:00. En el menú **Activadores** (reloj) los verás listados.

**Ajustes** (al inicio de `Codigo.gs`): `HORAS` para cambiar las horas, `ZONA` para la zona horaria, `ETIQUETA_IMPORTANTE` para destacar otra etiqueta (o `''` para ninguna). Después de cambiar `HORAS`, vuelve a ejecutar `programar`.

**Notas:**
- Google ejecuta los activadores con una variación de hasta unos 15 minutos sobre la hora pedida.
- Para pausar los avisos, ejecuta `desprogramar`.
- Si usas la nube, **desactiva las tareas de Windows** para no recibir el resumen duplicado: `schtasks /Delete /TN "Resumen Gmail Telegram 1900" /F` y lo mismo con `2100`.
- El token de Telegram queda guardado en las propiedades de tu proyecto de Apps Script, no en el código. Quien tenga acceso de edición a ese proyecto puede verlo.
- Los errores se ven en **Ejecuciones** (menú izquierdo). Los más comunes: faltan las propiedades `TELEGRAM_TOKEN` o `TELEGRAM_CHAT`, o no se agregó el servicio Gmail API en el paso 4. Si llega el texto pero no las gráficas, mira ese mismo registro: una gráfica que falle no impide las demás ni el texto.
- Si pegas una versión nueva de `Codigo.gs`, no hace falta volver a ejecutar `programar`, salvo que cambies `HORAS`.

### 11.6 Comandos y botones de papelera del bot personal

En el proyecto del resumen de Telegram (el de tu cuenta), el bot responde a comandos y permite mover correos a la papelera.

**Para activarlo (una sola vez), en el editor de Apps Script:**

1. Pega el `Codigo.gs` más reciente de `Kit para otra cuenta\nube\` y guarda con Ctrl+S.
2. Ejecuta `registrarComandos` (hace que `/estado` aparezca en el menú del bot).
3. Ejecuta `activarBotones` **una sola vez**. Crea un activador que revisa Telegram cada minuto.

**Comandos** (solo los obedece tu chat; los de otros chats se ignoran):

| Comando | Qué hace |
|---|---|
| `/estado` | Resumen de las últimas 24 horas, con gráficas y botones 🗑️ |
| `/estado 6` | Últimas 6 horas |
| `/estado 3d` | Últimos 3 días (hasta 30) |
| `/ayuda` | Lista los comandos |

La respuesta tarda hasta un minuto, porque el bot revisa Telegram una vez por minuto. Un `/estado` no se puede repetir más de una vez por minuto y no altera el «desde el último resumen» de las 19:00 y 21:00.

**Mover a la papelera con los botones**

1. Bajo cada resumen aparece un botón `🗑️ Papelera: <remitente> (n)` por cada uno de los 5 remitentes que más escribieron. El número es lo recibido en la ventana del resumen.
2. Al pulsarlo, el bot responde en hasta un minuto con «⚠️ ¿Mover a la papelera N conversaciones de …?» y los botones **✅ Sí, a la papelera** y **❌ Cancelar**. N cuenta **todas** las conversaciones de ese remitente en Gmail, no solo las recientes.
3. Solo al pulsar **Sí** las mueve. Responde «🗑️ Listo: N conversaciones … están en la papelera de Gmail».

**Candados:**

- Solo va a la **papelera** (se recupera 30 días), nunca borra definitivamente.
- No toca las conversaciones con **estrella** ni las de la etiqueta `ETIQUETA_IMPORTANTE` (por defecto `Ofertas y entrevistas`).
- Solo obedece al chat de `TELEGRAM_CHAT`.
- Los botones caducan a las 6 horas; el bot lo avisa y pide un `/estado` nuevo.
- Un botón ya confirmado no se puede repetir, y cada orden de Telegram se procesa una sola vez.
- Para desactivar los botones sin quitar el resumen, pon `var BOTONES_BORRADO = false;`.

> **Cuidado con lo que se mueve.** Un remitente como `no-reply@accounts.google.com` agrupa avisos de seguridad de tu cuenta. Revisa el remitente antes de confirmar. Lo movido se recupera desde **Papelera** en Gmail durante 30 días; para liberar espacio hay que **vaciar la papelera**.

**Usa un bot distinto al del dashboard web.** Este bot lee sus propios mensajes para detectar los botones, y eso le quitaría a la página los mensajes de vinculación de las demás personas.

### 11.7 Si los botones o `/estado` no responden

Ejecuta `diagnosticoBotones`: te manda a Telegram un informe con el estado de cada pieza. Y ejecuta `probarBotones` justo después de pulsar un botón: procesa lo pendiente en ese momento y te manda un informe con lo que recibió y procesó.

| Informe | Causa | Solución |
|---|---|---|
| `Activador revisarBotones: 0` | Nadie escucha: se desactivó o nunca se creó | Ejecutar `activarBotones` una vez |
| `Activador revisarBotones: 2` o más | Activadores duplicados | `desactivarBotones` y luego `activarBotones` una vez |
| `Hay un webhook activo` | Un webhook bloquea la lectura de mensajes | Quitarlo con `deleteWebhook` en la API de Telegram |
| `Pendientes` no baja y el activador existe | El activador no corre o está inhabilitado por fallos | Mirar **Ejecuciones** filtrando por `revisarBotones` y recrear el activador |
| `botones: 0` tras pulsar | Telegram no entregó el clic, o se pulsó un botón de un resumen antiguo | Pedir `/estado` y pulsar un botón del mensaje **nuevo** |
| `⌛ Ese botón expiró` | Pasaron más de 6 horas | `/estado` y usar los botones nuevos |
| Llega el resumen repetido | Orden reprocesada o activadores duplicados | Ya hay filtros contra repeticiones; revisar **Activadores** |
| `⚠️ No pude procesar eso: …` | Error al ejecutar la orden | El texto dice el motivo |

Un detalle técnico aprendido: el bot revisa Telegram cada minuto, y para entonces Telegram ya considera «vencido» el aviso del clic (`answerCallbackQuery`). Ese error es normal y el código lo ignora, pero una versión anterior se detenía ahí y por eso los botones no respondían.

### 11.8 Otros canales

- **Correo a tu Gmail:** `vigilar.py` lo soporta con una **contraseña de aplicación** (<https://myaccount.google.com/apppasswords>, requiere verificación en dos pasos). `resumen_telegram.py` solo envía por Telegram.
- **SMS y WhatsApp automáticos:** no se pueden sin un proveedor de pago (Twilio u otro) o la API de WhatsApp Business.

Prueba el aviso de fin de descarga con `python vigilar.py --probar`. Sin configurar nada, ese resumen queda en `AVISO_TERMINADO.txt`.

---

## 12. Lista de verificación para la cuenta nueva

- [ ] Python y librerías de Google instalados
- [ ] Carpeta del kit creada, sin archivos de la cuenta original
- [ ] Proyecto de Google Cloud con la API de Gmail activa
- [ ] Cuenta nueva agregada como usuario de prueba
- [ ] `client_secret.json` descargado y renombrado
- [ ] `python analizar_gmail.py` terminó con el total esperado de correos
- [ ] Dashboard revisado y lista de remitentes a limpiar anotada
- [ ] `etiquetas.json` editado para la cuenta nueva
- [ ] `--local` y `--simular` dan la misma cifra
- [ ] Correo importante protegido con una etiqueta
- [ ] `--aplicar` ejecutado (etiquetas y reglas)
- [ ] Borrado a papelera con `--proteger`
- [ ] Papelera revisada y vaciada
- [ ] `python sincronizar.py` (o `actualizar_dashboard.bat`) ejecutado y dashboard actualizado
- [ ] Bot de Telegram creado, `notificar.json` rellenado y `python resumen_telegram.py` recibido en el celular
- [ ] Resumen programado (`programar_resumen_telegram.bat`), si se quiere automático
- [ ] O resumen en la nube instalado (sección 11.5) y tareas de Windows desactivadas
- [ ] Página web (carpeta `docs`): ID de cliente de Google en `config.js` y usuarios de prueba agregados (sección 14)
- [ ] O Apps Script web desplegado, con `TELEGRAM_TOKEN` y `TELEGRAM_BOT_USER` si quieres alertas (sección 15)
- [ ] Bot personal: `activarBotones` ejecutado y `/estado` responde sin tocar el editor (sección 11.6)
- [ ] Tokens de bot regenerados con `/revoke` si quedaron visibles en algún chat
- [ ] App de Google Cloud pasada a *En producción* para que el token no caduque cada 7 días
- [ ] Carpeta del kit fuera de OneDrive o sin `cache_gmail.db`, `datos_gmail.js` ni `token*.json` si es compartida

---

## 13. Referencia rápida de comandos

```powershell
# Descargar y analizar
python analizar_gmail.py
python analizar_gmail.py --resumen

# Organizar
python organizar_correos.py --local
python organizar_correos.py --simular
python organizar_correos.py --aplicar
python organizar_correos.py --aplicar --solo-etiquetar        # sin sacar de la bandeja
python organizar_correos.py --aplicar --sin-reglas            # sin reglas automáticas
python organizar_correos.py --aplicar --solo "GitHub"         # solo una carpeta
python organizar_correos.py --aplicar --borrar --proteger "NOMBRE"
python organizar_correos.py --aplicar --definitivo --si       # irreversible

# Reglas
python crear_regla.py --listar
python crear_regla.py --etiqueta "X" --desde dominio.com --saltar-bandeja
python crear_regla.py --eliminar ID

# Proteger y mantener
python buscar_empleo.py --listar
python buscar_empleo.py --etiquetar "Ofertas y entrevistas" --aplicar
python sincronizar.py               # actualizar la data (o doble clic en actualizar_dashboard.bat)
python sincronizar.py --simular     # solo contar diferencias
python vigilar.py

# Telegram
python resumen_telegram.py --buscar-chat
python resumen_telegram.py --simular
python resumen_telegram.py --sincronizar --dias 1
```

---

## 14. Dashboard publicado: que otras personas conecten su cuenta

Además del dashboard local, hay una versión **web** que cualquiera de un grupo pequeño puede usar: abre el enlace, pulsa *Conectar con Google* y ve el análisis de su propia cuenta. Está en `docs\` y se publica con **GitHub Pages**, gratis.

### 14.1 Cómo funciona y qué garantiza

- Es una página estática. **No hay servidor ni base de datos**: la descarga de los correos y el análisis ocurren en el navegador de cada persona. Quien publica la página no ve los correos de nadie.
- Pide solo el permiso `gmail.metadata`: cabeceras, etiquetas y tamaños. No lee el contenido y no puede modificar ni borrar.
- Cada persona puede revocar el acceso con el botón **Desconectar** o en <https://myaccount.google.com/permissions>.
- El análisis es el mismo del dashboard local, escrito en JavaScript. Se comprobó contra el script de Python sobre los mismos 16.265 correos: coinciden el total, el espacio, los sin leer, los boletines, las categorías, las etiquetas, las fechas y los remitentes. Solo difieren 14 asuntos, por un espacio final y un carácter invisible que la versión web limpia.

### 14.2 Límites de Google que conviene conocer

| Alcance | Qué pasa |
|---|---|
| **Grupo pequeño (hasta 100 personas que agregas a mano)** | Funciona. Ven el aviso de «app no verificada» y el permiso caduca a los 7 días, así que deben volver a conectar |
| **Público abierto** | Gmail es un permiso restringido: Google exige verificar la app y una auditoría de seguridad anual de pago. No es viable para uso personal |

Quien publique la página es responsable de lo que ocurra con los datos de quienes la usen, aunque no los vea. Conviene decir claramente qué lee y qué no, como hace la pantalla de acceso.

### 14.3 La página ya publicada

El repositorio contiene **toda la carpeta del proyecto** (guía, kit, Apps Script y la página). La página vive en la carpeta `docs\`, y GitHub Pages publica esa carpeta.

- Repositorio: <https://github.com/hernandezjxs-alt/radiografia-gmail>
- Dirección pública: <https://hernandezjxs-alt.github.io/radiografia-gmail/>

Hasta completar el paso 14.4, la página muestra el aviso «Falta un paso de configuración» y el botón no funciona.

### 14.4 Configurar el acceso con Google (una vez, ~10 minutos)

1. Entra a <https://console.cloud.google.com/> y elige tu proyecto `Dashboard Gmail`, o crea uno nuevo.
2. **API y servicios → Biblioteca →** Gmail API → **Habilitar** (ya la tienes si hiciste el paso 2 de esta guía).
3. **Pantalla de consentimiento** (*Google Auth Platform → Público*): tipo **Externo**, estado **Prueba**. Agrega como **usuarios de prueba** el correo de cada persona que va a usar la página, incluido el tuyo. Máximo 100.
4. En **Acceso a los datos** (o *Permisos*), agrega el permiso `.../auth/gmail.metadata`.
5. **Credenciales → Crear credenciales → ID de cliente de OAuth.**
   - Tipo de aplicación: **Aplicación web** (no *App de escritorio*).
   - **Orígenes autorizados de JavaScript:** `https://hernandezjxs-alt.github.io` (sin barra final y sin `/radiografia-gmail`).
   - No hace falta URI de redireccionamiento.
6. Copia el **ID de cliente** (termina en `.apps.googleusercontent.com`). No hace falta el secreto.
7. En el repositorio, edita `config.js` y sustituye el texto de ejemplo:

   ```javascript
   window.GMAIL_CLIENT_ID = "123456-abcdef.apps.googleusercontent.com";
   ```

8. Guarda el cambio con un commit. GitHub Pages republica en uno o dos minutos. Si prefieres, pásame el ID de cliente y lo actualizo yo.

El ID de cliente **no es secreto** y puede estar en un repositorio público. Lo que nunca se debe publicar es el secreto del cliente (`client_secret`); esta página no lo usa.

### 14.5 Compartirlo con el grupo

1. Agrega a cada persona como usuario de prueba (14.4, paso 3).
2. Pásale la dirección pública.
3. Que elija cuántos correos analizar y pulse **Conectar con Google**. Verá «Google no ha verificado esta aplicación»: debe pulsar *Configuración avanzada → Ir a … (no seguro)* y aceptar.
4. Las opciones de tamaño son orientativas:

| Opción | Tiempo aproximado |
|---|---|
| Últimos 2.000 correos | 1 minuto |
| Últimos 5.000 | 2 minutos |
| Últimos 15.000 | 6 minutos |
| Todo el buzón | 10 minutos o más |

La descarga va a unos 40 a 50 correos por segundo, que es lo que permite la cuota de Google por usuario. Debe dejarse la pestaña abierta.

### 14.6 Actualizar la página

El repositorio está conectado a tu cuenta de GitHub. Para cambiar algo:

```powershell
cd "RUTA\A\proyecto"
git add -A
git commit -m "Describe el cambio"
git push
```

GitHub Pages republica solo. Para retirar la página: en GitHub, **Settings → Pages → Unpublish**, o borrar el repositorio.

### 14.7 Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| «Falta un paso de configuración» | `config.js` aún tiene el texto de ejemplo | Paso 14.4, punto 7 |
| «Error 400: origin_mismatch» | El origen autorizado no coincide con la dirección | Debe ser exactamente `https://hernandezjxs-alt.github.io`, sin ruta ni barra final |
| «Error 403: access_denied» | La persona no es usuario de prueba | Agrégala en la pantalla de consentimiento |
| La ventana de Google no se abre | El navegador bloquea ventanas emergentes | Permitirlas para este sitio |
| «Gmail respondió 403» o «Gmail API has not been used» | La Gmail API no está habilitada en el proyecto de ese ID de cliente | Paso 14.4, punto 2 |
| Deja de funcionar a la semana | En modo *Prueba* el permiso caduca a los 7 días | Volver a pulsar *Conectar con Google* |
| La descarga se detiene con mensaje de cuota | Demasiadas peticiones; la página reintenta sola | Esperar, o elegir menos correos |

---

## 15. Dashboard en Apps Script (alternativa a GitHub Pages)

La misma herramienta, publicada como **aplicación web de Apps Script**. Cada persona abre el enlace, autoriza el script con su cuenta y ve el análisis de su buzón. No hace falta crear un ID de cliente de OAuth ni agregar usuarios de prueba uno por uno. Los archivos están en `Apps Script web\`: `Codigo.gs`, `Index.html`, `appsscript.json` y `appsscript.con_borrado.json`.

### 15.1 Comparación con GitHub Pages

| | GitHub Pages (sección 14) | Apps Script web (esta sección) |
|---|---|---|
| Configuración | ID de cliente en Google Cloud + usuarios de prueba | Publicar y pasar el enlace |
| Velocidad | ~40-50 correos/s, directo desde el navegador | Más lenta: el servidor entrega en tandas |
| Dirección | `usuario.github.io/...` | `script.google.com/macros/s/.../exec` |
| Descargas y portapapeles | Funcionan | Pueden verse limitados por el marco de la página |
| Alertas por Telegram por persona | No | Sí |
| Borrado opcional | No | Sí (desactivado por defecto) |

### 15.2 Desplegar

1. En <https://script.google.com> crea un proyecto **nuevo** (por ejemplo `Radiografia Gmail Web`), distinto del que envía tu resumen personal.
2. Pega `Codigo.gs` en `Código.gs`.
3. Con **+ → HTML** crea un archivo llamado exactamente `Index` (con la I mayúscula, sin `.html`, sin espacios ni signos) y pega `Index.html`.
4. En **Configuración del proyecto** marca *Mostrar el archivo de manifiesto*, abre `appsscript.json` y pega el del kit. Ese manifiesto trae el servicio **Gmail API**; si no lo pegas, agrégalo con **Servicios (+) → Gmail API**.
5. **Implementar → Nueva implementación → Aplicación web.** *Ejecutar como:* **Usuario que accede**. *Quién tiene acceso:* **Cualquier usuario con cuenta de Google.**
6. Autoriza (si Google avisa que la app no está verificada: *Configuración avanzada → Ir a … (no seguro)*) y copia la URL `/exec`.
7. Cada cambio de código requiere **Implementar → Administrar implementaciones → ✏️ → Nueva versión**; sin eso, la URL sigue con el código anterior.

### 15.3 Alertas por Telegram para cada persona

Un botón flotante **🔔 Alertas por Telegram** permite a cada persona vincular su Telegram y elegir a qué horas recibir su resumen (08:00, 13:00, 19:00 o 21:00, hora de Chile).

**El administrador configura una vez**, en *Configuración del proyecto → Propiedades de la secuencia de comandos*:

| Propiedad | Valor |
|---|---|
| `TELEGRAM_TOKEN` | token del bot del grupo |
| `TELEGRAM_BOT_USER` | usuario del bot, sin `@` |

**Usa un bot exclusivo para el grupo** (por ejemplo `radiografia_gmail_bot`) y distinto del bot personal. El token solo lo lee el código del servidor y nunca se envía a la página.

**Cada persona:** pulsa el botón → *Generar enlace* → *Abrir Telegram* → **START** → *Ya pulsé START, vincular* → elige las horas → *Guardar y activar*. Puede enviar una prueba o desvincularse cuando quiera. Su chat y sus horas se guardan en sus propias propiedades de usuario.

**Límites de este resumen:**

- Es solo texto: buzón, nuevos, bandejas y remitentes. Los permisos de solo metadatos no permiten buscar ni calcular tendencias, y las gráficas siguen solo en el resumen personal.
- Cubre los 100 correos más recientes; si recibes más entre un resumen y otro, aparece con un `+`.
- Vincular lee los mensajes recientes del bot; con muchas personas a la vez, alguna puede tener que reintentar.
- Si el permiso de la persona caduca, sus alertas dejan de llegar hasta que vuelva a abrir la página y reautorice.
- `tgProbar` y el resto de funciones `tg…` se usan desde la página; ejecutarlas desde el editor da «Primero vincula tu Telegram».

### 15.4 Borrado opcional desde la página

Viene **apagado**. Con él, cada remitente de las tablas de **Remitentes** y **Bandejas** tiene un botón 🗑️ que cuenta los correos, pide confirmación y los manda a la **papelera** (nunca borra definitivamente y no toca los destacados con estrella).

Para encenderlo:

1. Pega `appsscript.con_borrado.json` en lugar de `appsscript.json` (usa el permiso `gmail.modify`).
2. Agrega la propiedad `PERMITIR_BORRADO` = `1`.
3. Crea una nueva versión del despliegue y autoriza de nuevo.

La pantalla de acceso cambia sola y deja de decir «no puede modificar ni borrar nada».

> **Recomendación:** no lo enciendas en el enlace que compartes con el grupo. El permiso `gmail.modify` da control sobre todo el correo. Crea un proyecto aparte, solo para ti o para gente de total confianza, y deja el compartido solo de lectura.

### 15.5 Problemas encontrados al desplegar

| Síntoma | Causa | Solución |
|---|---|---|
| «No se ha encontrado el archivo HTML denominado Index» | El archivo se llamaba distinto (en un caso tenía una coma) | Renombrarlo a exactamente `Index` y crear una versión nueva |
| «Gmail API has not been used in project … or it is disabled» (403) | La API de Gmail no está habilitada en el proyecto de Google Cloud del script | **Servicios (+) → Gmail API → Agregar**, o cambiar a un proyecto de Cloud con la API activa |
| «Primero vincula tu Telegram» al ejecutar `tgProbar` | Esa función usa el Telegram vinculado de quien la ejecuta | Vincular desde la página, o probar con el botón «Enviar una prueba ahora» |
| El panel dice «El administrador aún no configuró el bot» | Faltan `TELEGRAM_TOKEN` o `TELEGRAM_BOT_USER`, o están mal escritas | Revisar las propiedades del script y crear una versión nueva |
| La URL muestra el código antiguo | No se creó una versión nueva | **Administrar implementaciones → ✏️ → Nueva versión** |

### 15.6 Seguridad y privacidad

- El script no usa hojas, bases de datos ni envía los correos a ningún otro sitio. El análisis se hace en el navegador de quien lo abre.
- El administrador es responsable de lo que el código haga con los datos de quienes lo usen, aunque no los vea. Quien tenga acceso de edición al proyecto puede ver el código y las propiedades del script.
- Si un token de bot queda visible (en un chat, una captura o un documento), **regenerarlo** con `/revoke` en `@BotFather` y actualizar la propiedad.
- El tope de usuarios y la caducidad de permisos de las apps no verificadas aplican también aquí.
