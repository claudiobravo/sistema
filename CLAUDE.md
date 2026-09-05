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

## Qué queda en la rama `claude/trabajo-en-tren-2q7luc`

Trabajo hecho el 05/09/2026 antes de descubrir que GLIVO ya existía. Se deja como
registro de lo que se probó, sin publicar:

- Sincronización con reintentos y fusión por hora contra `registro.json`.
- Selector de día e historial, para rellenar días pasados.
- Puertas que no desaparecen al caducar y avisos de PUERTA ROJA.
- Sello de rango en SVG.
- Pruebas en `pruebas/` (64 comprobaciones).

De todo eso, lo único que se llevó a GLIVO fueron dos fechas límite que allí
faltaban: el **cierre de AGAUR del 28/09** y la **salida de España del 15/01/2027**.
