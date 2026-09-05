# EL SISTEMA

PWA de un solo fichero. Sin build, sin dependencias, sin gestor de paquetes.
Se abre `index.html` y funciona; el service worker la deja usable sin cobertura.

```
index.html            la app entera: markup + CSS + JS
sw.js                 caché offline (var CACHE = 'sistema-vN')
manifest.webmanifest  metadatos PWA
icon-180.png/512.png  iconos
```

Los datos del usuario viven en `localStorage` y se sincronizan contra la API de
GitHub. No hay servidor. No hay tests ni linter: la validación es abrir la app
en un navegador y comprobar que arranca sin errores de consola.

## Trabajo en paralelo

Varias sesiones remotas trabajan a la vez sobre este repo, cada una en su
contenedor y su rama, sin verse entre ellas. Como toda la app está en
`index.html`, "qué fichero tocas" no reparte nada: **lo que reparte es la zona**.

Al arrancar, el hook `.claude/hooks/session-start.sh` te dice qué zonas están
ocupadas por otras ramas vivas. Ese reparto no es informativo, es la regla.

1. **Una zona, una sesión.** No edites una zona que el reparto marca como
   ocupada. Si el encargo cae ahí, dilo al usuario y propón alternativa antes
   de tocar nada.
2. **`git fetch origin` antes de escribir** en `index.html`. El reparto del
   arranque envejece en cuanto otra sesión pushea.
3. **Commit y push pronto.** Tu rama es lo que hace visible tu reserva a las
   demás sesiones. Una zona que estás editando pero no has pusheado es
   invisible para ellas: para el resto del mundo, está libre.
4. **Nunca reescribas la rama de otra sesión**: ni `push --force`, ni rebase,
   ni amend sobre trabajo ajeno.
5. **Integra desde `origin/main`**, nunca fusiones la rama de otra sesión salvo
   que el usuario lo pida.
6. **No toques `var CACHE` de `sw.js`** en una rama de trabajo. Todas las
   sesiones querrían subir el mismo número y chocarían en esa línea. El número
   se sube una sola vez, al integrar en `main`.

Consultar el reparto en cualquier momento:

```bash
.claude/hooks/session-start.sh              # informe completo
.claude/scripts/zonas.sh origin/claude/RAMA # zonas de una rama concreta
```

### Zonas

Se derivan de los marcadores del propio `index.html`, no de números de línea,
así que siguen valiendo cuando el fichero crece:

| marcador en el fichero | zona |
|---|---|
| `<style>` | CSS (estilos) |
| `<!-- ══ HOY ══ -->` y hermanos | markup: HOY / ESTADO / MISIONES / PUERTAS |
| `// ── estado ──` y hermanos | js: estado / guardado + sync / render / enlaces de campos |

Para crear una zona nueva, añade un marcador con ese mismo formato y el reparto
la reconoce sola.

## Estilo del código

JavaScript de navegador, sin framework y sin transpilar: `var`, `function`,
nada de `import`. Funciones cortas y compactas, a menudo en una línea. Todo en
español: nombres de función (`pintarHoy`, `expTotal`, `esDescanso`), comentarios
y textos de interfaz. Al añadir código, imita lo que ya hay alrededor.
