#!/bin/sh
# Lanza todas las pruebas. Se para en la primera que falle.
set -e
cd "$(dirname "$0")/.."
node pruebas/sync.test.js
node pruebas/dias.test.js
node pruebas/puertas.test.js
echo
echo "Todas las pruebas en verde."
