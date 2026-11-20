# Radiografía Gmail

Herramientas para analizar y limpiar un buzón de Gmail, con resúmenes y comandos por Telegram.
Página publicada: <https://hernandezjxs-alt.github.io/radiografia-gmail/>

| Carpeta | Contenido |
|---|---|
| `docs/` | La página web (GitHub Pages): dashboard con inicio de sesión de Google, instalable como app en el celular (PWA) |
| `Apps Script web/` | Versión como aplicación web de Apps Script: análisis por persona, alertas por Telegram y borrado opcional |
| `Kit para otra cuenta/` | Scripts de Python, dashboard local y resumen en la nube, listos para copiar a otra cuenta |
| `Guia paso a paso - ...md / .docx` | Guía completa, de las credenciales al despliegue (secciones 0 a 15) |

## Privacidad

- La página corre en el navegador: los correos van de Google a quien la usa y no pasan por ningún servidor propio. Solo lee cabeceras (permiso `gmail.metadata`).
- Este repositorio no contiene credenciales, tokens, cachés ni datos de ningún buzón (ver `.gitignore`).
- Si un token de bot queda visible en algún sitio, regenéralo con `/revoke` en BotFather.
