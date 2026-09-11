# Este repositorio está RETIRADO

Desde el **05/09/2026**. No le añadas funciones.

## Dónde vive El Sistema de verdad

En `claudiobravo/Glivo-Robot`, como la pestaña **Sistema** de GLIVO HUB
(`el-sistema.html` + `el-sistema-server.py`). El progreso —nivel, rango, racha y
EXP— se guarda en la bóveda de Obsidian del MSI, en
`~/cerebro/Panel/sistema-progreso.md`, con git.

**Si te piden mejorar "El Sistema", es aquel repo, no este.**

## Qué fue esto

Una PWA suelta, un solo `index.html` servido por GitHub Pages, con los datos en
`localStorage` y copia en `claudiobravo/sistema-datos/registro.json`.

Resolvía el mismo problema que GLIVO, peor y por separado, y durante un tiempo
las dos llevaron la cuenta a la vez con reglas que no coincidían: aquí la EXP
iba de 500 en 500 por nivel y todo se escribía a mano; en GLIVO va de 50 en 50 y
las misiones se detectan solas del registro diario. Por eso los números nunca
cuadraban entre el móvil y el portátil.

## Qué hay sin publicar (revisión del 11/09/2026)

Tres ramas en GitHub, ninguna fusionada, sin pull requests ni incidencias
abiertas. Lo publicado en GitHub Pages es solo esta nota. Nada de lo de abajo
está activo.

### `claude/trabajo-en-tren-2q7luc` — archivo, no tocar

Trabajo hecho el 05/09/2026 antes de descubrir que GLIVO ya existía. Se deja como
registro de lo que se probó, sin publicar:

- Sincronización con reintentos y fusión por hora contra `registro.json`.
- Selector de día e historial, para rellenar días pasados.
- Puertas que no desaparecen al caducar y avisos de PUERTA ROJA.
- Sello de rango en SVG.
- Pruebas en `pruebas/`: unas 65 comprobaciones, de las que 24 corren solas.
  Las otras necesitan un navegador de pruebas (`npm i playwright-core`); si
  falta, el lote se para con código 2 en vez de darse por bueno.

Sube la caché del service worker a `sistema-v3` y lo publicado está en `v1`.

De todo eso, lo único que se llevó a GLIVO fueron dos fechas límite que allí
faltaban: el **cierre de AGAUR del 28/09** y la **salida de España del 15/01/2027**.

### `claude/pregunta-3fompb` — no fusionar tal cual

Añade el reparto de zonas (`.claude/hooks/session-start.sh` y
`.claude/scripts/zonas.sh`) para que varias sesiones en paralelo no se pisen
dentro de `index.html`. Eso es aprovechable.

El problema es que arrastra el CLAUDE.md **anterior** a la retirada: fusionarla
borraría esta nota. Además remite a `pruebas/`, que en esa rama no existe. Si se
rescata, hay que llevarse solo `.claude/`.

### `claude/whatsapp-vinted-wallapop-bot-xmx0ij` — lo único vivo

Un bot self-hosted del 07/09/2026 que registra las ventas de Vinted y Wallapop
desde un grupo de WhatsApp (gateway en Docker, backend FastAPI, extracción con
LLM, SQLite), más `tools/puente_glivo.py` para que no haya dos contabilidades.
Es autocontenido: no es El Sistema ni una función de esta PWA, y su sitio es un
repositorio propio.

Sus ~100 pruebas pasan sin red, pero nunca ha visto una etiqueta real. Queda por
hacer, y está detallado en `whatsapp-ventas/README.md`:

- Los seis pasos de montaje: secretos, contenedores, QR de la SIM secundaria,
  identificador del grupo, webhook y prueba de humo. Ninguno se ha dado.
- Afinar los patrones de códigos de seguimiento: hoy los rangos se solapan y el
  aviso a mano salta casi siempre.
- Comprobar `PDF_MIN_CARACTERES` contra una etiqueta escaneada de verdad, y la
  forma real del mensaje del webhook de Evolution.
- Programar el puente con Glivo: existe, pero nadie lo lanza solo.
- Su README dice 101 pruebas en un sitio y 89 en otro; el 89 está viejo.
