# Radiografía de tu Gmail

Dashboard que analiza una cuenta de Gmail y muestra de dónde viene el correo, qué ocupa espacio y qué conviene limpiar: tarjetas, filtros por mes, etiqueta, dominio y tamaño, gráficas históricas y de torta, bandejas (Principal, Promociones, Social, Notificaciones) y un plan de limpieza con consultas listas para pegar en Gmail.

## Privacidad

- **Todo ocurre en el navegador.** Los datos van de Google a la pestaña de quien usa la página. No hay servidor propio ni base de datos, y nada se guarda.
- **Solo lee metadatos** (remitente, asunto, fecha, tamaño, etiquetas) con el permiso `gmail.metadata`. No lee el contenido de los correos y no puede modificar ni borrar nada.
- El botón **Desconectar** revoca el permiso. También se puede en <https://myaccount.google.com/permissions>.
- No hay cookies propias ni analítica.

## Cómo publicarlo (GitHub Pages)

1. Repositorio público → **Settings → Pages → Deploy from a branch → `main` / `/ (root)`**.
2. En [Google Cloud Console](https://console.cloud.google.com/) crea un proyecto y activa la **Gmail API**.
3. **Pantalla de consentimiento** → tipo *Externo* → estado *Prueba* → agrega como **usuarios de prueba** a quienes la van a usar (hasta 100).
4. **Credenciales → Crear credenciales → ID de cliente de OAuth → Aplicación web**. En *Orígenes autorizados de JavaScript* pon `https://TU_USUARIO.github.io` (sin barra final ni ruta).
5. Copia el ID de cliente en `config.js` y haz commit.

## Límites a tener en cuenta

- Mientras la app esté en modo *Prueba*, solo entran los usuarios agregados, ven el aviso de «app no verificada» y el permiso caduca a los 7 días.
- Abrirla al público general exige que Google verifique la app y una auditoría de seguridad anual, porque Gmail es un permiso restringido. Esta herramienta está pensada para un grupo pequeño.
- La descarga desde el navegador es más lenta que un script local: unos 40 a 50 correos por segundo. Por eso se puede elegir cuántos correos analizar.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `index.html` | El dashboard y la pantalla de acceso |
| `cargador.js` | Inicio de sesión con Google y descarga de los metadatos |
| `analisis.js` | Convierte los metadatos en los datos del dashboard |
| `config.js` | ID de cliente de Google (no es secreto) |
| `chart.umd.min.js` | Librería de gráficos (Chart.js), incluida para no depender de internet |
