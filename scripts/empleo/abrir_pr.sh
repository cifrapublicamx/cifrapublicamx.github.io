#!/usr/bin/env bash
# Cifra Pública | Folio 003 | Abre (o actualiza) un PR con los archivos que cambió un workflow.
# Solo lo usan los workflows de GitHub Actions; el merge siempre lo haces tú.
#
# Uso: abrir_pr.sh <rama> <título> <archivo_con_el_texto_del_PR> <ruta> [<ruta> ...]
set -euo pipefail

rama="$1"; titulo="$2"; cuerpo="$3"; shift 3
base="${BASE_REF:-main}"

rutas=()
for r in "$@"; do [ -e "$r" ] && rutas+=("$r"); done
if [ "${#rutas[@]}" -eq 0 ]; then echo "No hay archivos que subir."; exit 0; fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git switch -C "$rama"
git add -A -- "${rutas[@]}"
if git diff --cached --quiet; then
  echo "Sin cambios: no hace falta PR."
  echo "Sin cambios: no hace falta PR." >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
  exit 0
fi
git commit -q -m "$titulo"
git push -q --force -u origin "$rama"

texto=$(mktemp)
if [ -f "$cuerpo" ]; then
  python3 - "$cuerpo" "$texto" <<'PY'
import sys
t = open(sys.argv[1], encoding="utf-8").read()
if len(t) > 60000:  # GitHub corta el texto del PR en 65,536 caracteres
    t = t[:60000] + "\n\n(Sigue en el archivo del PR.)\n"
open(sys.argv[2], "w", encoding="utf-8").write(t)
PY
else
  echo "(El workflow no generó texto para el PR.)" > "$texto"
fi
echo "" >> "$texto"
echo "Generado por el workflow «${GITHUB_WORKFLOW:-local}», corrida ${GITHUB_RUN_ID:-local}." >> "$texto"

if [ "$(gh pr view "$rama" --json state -q .state 2>/dev/null || true)" = "OPEN" ]; then
  gh pr edit "$rama" --title "$titulo" --body-file "$texto"
  echo "PR actualizado: $rama" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
else
  url=$(gh pr create --base "$base" --head "$rama" --title "$titulo" --body-file "$texto")
  echo "PR abierto: $url" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
fi
