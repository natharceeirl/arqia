# ARQIA

Asistente de diseño arquitectónico basado en BIM e inteligencia artificial. Proyecto para el Hackathon BIM + IA UNSA 2026, Reto 1.

ARQIA entrevista al cliente, genera tres alternativas con un motor paramétrico determinista, las compara con indicadores calculados y exporta el modelo en IFC4 verificado.

## Cómo está construido

| Parte | Tecnología | Carpeta |
| --- | --- | --- |
| Motor paramétrico | Python, Shapely | `backend/motor` |
| Modelo BIM y exportación IFC | IfcOpenShell (IFC4) | `backend/bim` |
| Avisos del lugar | Base de reglas en YAML | `backend/reglas` |
| Asistente | Claude API con herramientas y verificador de cifras | `backend/ia` |
| API | FastAPI | `backend/app` |
| Interfaz | React, TypeScript, Vite, React Three Fiber | `frontend` |

Principio: la IA pregunta, interpreta y explica; el motor calcula. Ninguna área, dimensión ni indicador sale de la IA, y un verificador descarta cualquier frase del asistente con cifras que no existan en los datos.

## Ejecutar en local

```bash
# API
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Interfaz (otra terminal)
cd frontend
npm install
npm run dev
```

Sin la variable `ANTHROPIC_API_KEY`, la entrevista funciona como formulario guiado. Con ella, el Asistente ARQIA usa Claude.

Pruebas del motor, del IFC y de la entrevista:

```bash
cd backend && python -m pytest -q
```

## Desplegar en Render

1. En Render: **New → Web Service**, conecta este repositorio. Render detecta el `Dockerfile`.
2. En **Environment**, agrega `ANTHROPIC_API_KEY` con la clave de Anthropic Console.
3. Opcional: `ARQIA_MODELO` para cambiar el modelo de Claude.
4. Cada cambio subido a la rama principal se publica solo.

La misma URL sirve la interfaz y la API (`/api/...`).

### Interfaz en Vercel (opcional)

Publica la carpeta `frontend` en Vercel con la variable `VITE_API_URL` apuntando a la URL de Render. En Render, define `ARQIA_CORS` con el dominio de Vercel.

## Limitaciones

Lote rectangular y plano; tres estrategias fijas; muros a ejes; materiales de representación. Los resultados son preliminares y requieren revisión profesional, estudio de mecánica de suelos y certificado de parámetros urbanísticos.
