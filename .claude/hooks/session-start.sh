#!/bin/bash
# SessionStart — reparto de trabajo entre sesiones paralelas.
#
# EL SISTEMA entero vive en index.html. Dos sesiones que lo editen a la vez
# chocan. Este hook no bloquea nada: informa. Al arrancar, cada sesión ve qué
# zonas están ya ocupadas por otras ramas vivas y elige otra cosa que hacer.
#
# Nunca debe tumbar el arranque: pase lo que pase, sale con 0.

set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
command -v git >/dev/null 2>&1 || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

BASE="origin/main"
DIAS_VIVA=21          # una rama sin tocar más tiempo ya no se considera activa
MAX_RAMAS=8

timeout 45 git fetch --prune origin >/dev/null 2>&1 \
  || echo "[aviso] no se pudo contactar con origin; el reparto usa datos locales."

ACTUAL="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
git rev-parse --verify -q "$BASE" >/dev/null 2>&1 || BASE="main"

echo "═══ REPARTO DE TRABAJO ENTRE SESIONES ═══"
echo "Rama de esta sesión: ${ACTUAL:-?}   ·   base: $BASE"
echo

mis_zonas="$(BASE="$BASE" .claude/scripts/zonas.sh HEAD 2>/dev/null)"
if [ -n "$mis_zonas" ]; then
  echo "Esta rama ya toca:"; echo "$mis_zonas"; echo
fi

ahora=$(date +%s)
otras=0
ocupadas=""

while read -r ts rama; do
  [ -n "${rama:-}" ] || continue
  corta="${rama#origin/}"
  [ "$corta" != "$ACTUAL" ] || continue
  edad=$(( (ahora - ts) / 86400 ))
  [ "$edad" -le "$DIAS_VIVA" ] || continue
  otras=$(( otras + 1 ))
  [ "$otras" -le "$MAX_RAMAS" ] || continue

  n=$(git rev-list --count "$BASE..$rama" 2>/dev/null || echo 0)
  [ "$n" -gt 0 ] || continue
  if [ "$edad" -eq 0 ]; then cuando="hoy"; else cuando="hace ${edad}d"; fi

  echo "▸ $corta  ($n commit(s), $cuando)"
  git log -1 --format='    último: %s' "$rama" 2>/dev/null
  z="$(BASE="$BASE" .claude/scripts/zonas.sh "$rama" 2>/dev/null)"
  if [ -n "$z" ]; then
    echo "$z"
    ocupadas="$ocupadas$z"$'\n'
  else
    echo "  · (no toca index.html)"
  fi
  otros="$(git diff --name-only "$BASE...$rama" 2>/dev/null | grep -v '^index.html$' | paste -sd', ' -)"
  [ -n "$otros" ] && echo "  · otros ficheros: $otros"
  echo
done < <(git for-each-ref --sort=-committerdate --format='%(committerdate:unix) %(refname:short)' \
           'refs/remotes/origin/claude/*' 2>/dev/null)

if [ "$otras" -eq 0 ]; then
  echo "No hay otras ramas de sesión activas. Campo libre."
else
  choque="$(printf '%s' "$ocupadas" | sort -u | comm -12 - <(printf '%s' "$mis_zonas" | sort -u) 2>/dev/null)"
  if [ -n "$choque" ]; then
    echo "⚠ CHOQUE: esta rama y otra sesión tocan la(s) misma(s) zona(s):"
    printf '%s\n' "$choque"
    echo "  → antes de seguir: git fetch origin && revisa esa rama, e integra en vez de reescribir."
  else
    echo "Zonas ocupadas por otras sesiones — no las toques sin avisar al usuario:"
    printf '%s' "$ocupadas" | sort -u
  fi
fi
echo
echo "Protocolo completo en CLAUDE.md (sección «Trabajo en paralelo»)."
echo "═════════════════════════════════════════"
exit 0
