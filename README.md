# TITAN Career Agent CLI

CLI local en Python para importar tu CV, descubrir ofertas desde RSS/Atom configurados o CSV, calcular afinidad por habilidades y pedir a agentes LLM una revisión y un borrador de CV adaptado por idioma.

## Lo que hace

- Importa CV PDF, DOCX, TXT o Markdown y lo conserva en un directorio privado local.
- Lee fuentes RSS/Atom HTTPS que agregues manualmente; también admite CSV de vacantes.
- Deduplica ofertas por URL y ordena con una coincidencia literal explicable de habilidades.
- Genera revisión de fortalezas/brechas y CV adaptado como Markdown, más una auditoría JSON y mapa de evidencia.
- Puede encadenar un agente revisor con un redactor diferente (`ensemble`) o usar un único modelo.
- No aplica a empleos, no contacta empresas, no envía el CV a portales y no inventa un envío.

## Proveedores LLM

`claude-cli` y `codex-cli` llaman las herramientas instaladas en tu equipo. Para tareas de texto, Career Agent desactiva las herramientas integradas de Claude y usa el sandbox de solo lectura y modo efímero de Codex. [Claude Code CLI](https://code.claude.com/docs/en/cli-usage), [Codex no interactivo](https://developers.openai.com/codex/noninteractive).

También hay adaptadores para `anthropic-api`, `openai-api`, `ollama` local y `openai-compatible` (servicios que aceptan Chat Completions, sujeto a compatibilidad del endpoint). Los nombres y disponibilidad de modelos cambian; se configuran por variable de entorno o `--model`.

## Instalación

Python 3.10 o posterior. En Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
career-agent --help
```

En macOS/Linux activa con `source .venv/bin/activate` después de crear el entorno.

## Uso rápido

```powershell
career-agent init
career-agent profile import-cv C:\ruta\a\tu-cv.pdf
career-agent profile set-name "Tu nombre"
career-agent profile set-contact --email "tu@email.com" --phone "+56 ..." --location "Santiago"
career-agent profile set-skills "Python, SQL, Power BI, análisis de datos"
career-agent jobs import-csv examples/jobs.csv
career-agent jobs list
career-agent tailor ID_DE_OFERTA --provider ollama --model qwen3:8b --language es
```

Para usar feeds:

```powershell
career-agent feeds add "Fuente de empleos" "https://example.org/jobs.xml"
career-agent feeds list
career-agent jobs sync
```

Para llamar servicios cloud, define antes sus credenciales/modelos y confirma el envío de datos con `--allow-external`:

```powershell
$env:OPENAI_API_KEY = "..."
$env:CAREER_OPENAI_MODEL = "..."
career-agent tailor ID_DE_OFERTA --provider openai-api --allow-external --language en
```

Para proveedores OpenAI-compatible configura `CAREER_LLM_BASE_URL`, `CAREER_LLM_MODEL` y opcionalmente `CAREER_LLM_API_KEY`. Para Anthropic API usa `ANTHROPIC_API_KEY` y `CAREER_ANTHROPIC_MODEL`. Para Ollama local configura `CAREER_OLLAMA_MODEL`; por defecto usa `http://localhost:11434/v1/chat/completions`. El modo `--language auto` estima español o inglés; para otros idiomas indica el código directamente, por ejemplo `--language fr`.

Claude Code y Codex deben estar instalados y autenticados por separado. Para revisión y redacción con dos agentes:

```powershell
career-agent tailor ID_DE_OFERTA --provider ensemble --reviewer claude-cli --writer codex-cli --allow-external --language auto
```

Cada endpoint cloud recibe texto del CV y la oferta. Career Agent enmascara emails, teléfonos, URLs y el nombre si configuraste `set-name`; inspecciona el CV antes de autorizar. `--include-pii` incluye esos datos identificables y solo debe usarse cuando sea intencional.

## Archivos generados

Por defecto, todo queda en `~/.career-agent/` (en Windows, bajo tu perfil de usuario), fuera del checkout público:

```text
~/.career-agent/
  candidate.json       # CV extraído y habilidades
  jobs.json            # ofertas importadas/sincronizadas
  feeds.json           # URLs RSS/Atom configuradas
  output/<oferta>/
    tailored_cv.md     # borrador localizado
    review.md          # observaciones del agente
    audit.json         # IDs fuente y bloques aceptados/descartados
    evidence-map.json  # texto fuente por ID, solo local
```

Usa `--home RUTA` o `CAREER_AGENT_HOME` para elegir otro directorio privado. No guardes ese directorio dentro de este repositorio ni lo sincronices a Git público. Las credenciales van en el gestor de credenciales del CLI o variables de entorno; nunca en el JSON del perfil.

## Integridad y límites

- Cada bloque generado debe referenciar uno o más IDs de fragmentos del CV original. Los bloques sin referencias válidas se descartan y quedan anotados en `review.md`.
- Una referencia válida no demuestra que la paráfrasis sea correcta. Revisa fechas, títulos, métricas, traducciones y contexto contra el CV fuente antes de usar el resultado.
- El ranking es coincidencia literal de habilidades, no una predicción de contratación. La extracción de skills de RSS usa un vocabulario corto; CSV permite definirlas explícitamente.
- La búsqueda consulta solo feeds RSS/Atom HTTPS que configures e importaciones CSV. No hace scraping de bolsas de empleo.
- La herramienta prepara documentos para revisión humana; no postula ni automatiza formularios de terceros.
- El agente puede equivocarse o no producir JSON válido. El CV fuente se mantiene intacto y los borradores se generan como archivos separados.

## Licencia

MIT. Ver [`LICENSE`](LICENSE).
