# Pruebas de EL SISTEMA

Las pruebas leen `index.html` directamente. No hay copia del código que
mantener al día: si cambias la app, la prueba va contra lo que acabas de
escribir.

## Ejecutar

```sh
node pruebas/sync.test.js        # sin dependencias ni conexión
```

Las otras dos abren la app en un navegador de verdad:

```sh
npm i playwright-core            # una vez
node pruebas/dias.test.js
node pruebas/puertas.test.js
```

O todas de golpe:

```sh
sh pruebas/todas.sh
```

Se busca Chromium en las rutas habituales. Si no lo encuentra, dile dónde
está: `CHROMIUM=/ruta/a/chrome node pruebas/puertas.test.js`.

Cada fichero sale con código 0 si todo va bien y 1 si algo falla.

## Qué cubre cada una

| Fichero | Qué comprueba |
|---|---|
| `sync.test.js` | La sincronización con la red simulada: fusión por hora, móvil nuevo que se rellena desde GitHub, días vacíos que no borran, caída de red y reintento, choque de sha, y el cálculo de EXP y de la Misión Diaria. |
| `dias.test.js` | El selector de día y el historial: que los campos no se arrastren de un día a otro, que se pueda rellenar un día pasado, que no queden fichas vacías y que nada se pierda al recargar. |
| `puertas.test.js` | Que ninguna Puerta desaparezca al caducar, que las Rojas cerradas se marquen, y el aviso de Puerta Roja en la pantalla de Hoy. |

`puertas.test.js` deduce lo que espera de las Puertas declaradas en
`index.html` y de la fecha de hoy, así que no caduca cuando las Puertas
vayan cerrándose. Lo mismo con `dias.test.js`: calcula los días a partir de
hoy en vez de clavar fechas.

## Piezas

- `dom-falso.js` — un DOM mínimo para poder cargar la app en Node, sin navegador.
- `cargar.js` — extrae el `<script>` de `index.html`, lo ejecuta sobre ese DOM
  falso y deja a la vista sus funciones internas.
- `util.js` — comprobaciones, arranque del navegador y ayudas de fechas.
