#!/bin/bash
# zonas.sh <ref> [fichero]
#
# Imprime las ZONAS de <fichero> que <ref> ha modificado respecto de la base
# (por defecto origin/main). EL SISTEMA vive en un solo index.html, así que
# "qué fichero tocas" no distingue nada: lo que distingue es la zona.
#
# Las zonas se derivan de los marcadores del propio fichero, no de números de
# línea fijos, para que sigan siendo correctas cuando el código crezca.

set -uo pipefail

REF="${1:-}"
FICH="${2:-index.html}"
BASE="${BASE:-origin/main}"

[ -n "$REF" ] || { echo "uso: zonas.sh <ref> [fichero]" >&2; exit 2; }

tmp="$(mktemp)"; trap 'rm -f "$tmp" "$tmp.mapa"' EXIT
git show "$REF:$FICH" > "$tmp" 2>/dev/null || { echo "(sin $FICH en $REF)"; exit 0; }

# ── mapa de zonas: "linea|etiqueta", derivado de los marcadores ──
{
  # <!-- ══ NOMBRE ══ -->  (secciones de markup)
  grep -n -F '══' "$tmp" 2>/dev/null | LC_ALL=C sed 's/[^ -~]//g' \
    | sed -nE 's/^([0-9]+):.*<!--[[:space:]]*(.*[^[:space:]])[[:space:]]*-->.*/\1|markup: \2/p'
  # // ── nombre ──  (secciones de JS)
  grep -n -F '// ─' "$tmp" 2>/dev/null | LC_ALL=C sed 's/[^ -~]//g' \
    | sed -nE 's|^([0-9]+):[[:space:]]*//[[:space:]]*(.*[^[:space:]])[[:space:]]*$|\1\|js: \2|p'
  # bloques estructurales
  grep -n -E '^[[:space:]]*<head>'   "$tmp" | sed -E 's/^([0-9]+):.*/\1|head y metadatos/'
  grep -n -E '^[[:space:]]*<style>'  "$tmp" | sed -E 's/^([0-9]+):.*/\1|CSS (estilos)/'
  grep -n -E '^[[:space:]]*<body>'   "$tmp" | sed -E 's/^([0-9]+):.*/\1|markup: cabecera/'
  grep -n -E '^[[:space:]]*<script>' "$tmp" | sed -E 's/^([0-9]+):.*/\1|js: arranque y datos/'
} | sort -t'|' -k1,1n > "$tmp.mapa"

# ── líneas tocadas (lado nuevo del diff) → zona ──
git diff --unified=0 "$BASE...$REF" -- "$FICH" 2>/dev/null \
  | sed -nE 's/^@@ -[0-9,]+ \+([0-9]+)(,([0-9]+))? @@.*/\1 \3/p' \
  | while read -r ini len; do
      len="${len:-1}"; [ "$len" -eq 0 ] && len=1
      fin=$(( ini + len - 1 ))
      for (( l=ini; l<=fin; l++ )); do
        awk -F'|' -v L="$l" '$1<=L{z=$2} END{if(z!="")print z}' "$tmp.mapa"
      done
    done | sort -u | sed 's/^/  · /'
