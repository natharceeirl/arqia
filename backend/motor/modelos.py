"""Esquemas de datos de ARQIA.

El brief es la entrada que el usuario (directamente o con ayuda del asistente)
construye. Las alternativas son la salida del motor determinista.
Todas las longitudes en metros y las áreas en m².
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

TipoAmbiente = Literal["publico", "privado", "servicio"]
EstadoVerificacion = Literal["cumple", "no_cumple", "pendiente", "revision_profesional"]


class Ubicacion(BaseModel):
    distrito: Optional[str] = None
    ciudad: Optional[str] = "Arequipa"
    pais: str = "Perú"
    contexto: list[str] = Field(default_factory=list, description="Etiquetas del entorno: campiña, ladera, centro histórico…")


class Terreno(BaseModel):
    frente_m: Optional[float] = Field(None, gt=0, le=200)
    fondo_m: Optional[float] = Field(None, gt=0, le=400)
    retiro_frontal_m: Optional[float] = Field(None, ge=0, le=20)
    estudio_suelos: Optional[Literal["si", "no", "desconoce"]] = None


class Ambiente(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60)
    nivel: int = Field(..., ge=1, le=10)
    tipo: TipoAmbiente
    area_objetivo_m2: Optional[float] = Field(None, gt=0, le=5000)


class Presupuesto(BaseModel):
    moneda: str = "PEN"
    monto: Optional[float] = Field(None, gt=0)
    referencial: bool = True


class Preferencias(BaseModel):
    luz_natural: Optional[Literal["baja", "media", "alta"]] = None
    estilo: Optional[str] = None
    acceso_independiente_n2: Optional[bool] = None
    notas: Optional[str] = None


class Brief(BaseModel):
    nombre_proyecto: str = "Proyecto sin nombre"
    tipo_proyecto: Optional[str] = None
    ubicacion: Ubicacion = Field(default_factory=Ubicacion)
    terreno: Terreno = Field(default_factory=Terreno)
    niveles: Optional[int] = Field(None, ge=1, le=4)
    altura_piso_m: float = Field(3.0, ge=2.4, le=6.0)
    ambientes: list[Ambiente] = Field(default_factory=list)
    presupuesto: Presupuesto = Field(default_factory=Presupuesto)
    preferencias: Preferencias = Field(default_factory=Preferencias)
    # origen de cada dato: "usuario", "supuesto" o "asistente"
    origen: dict[str, str] = Field(default_factory=dict)

    @field_validator("ambientes")
    @classmethod
    def _nombres_unicos(cls, v: list[Ambiente]) -> list[Ambiente]:
        vistos = set()
        for a in v:
            clave = (a.nivel, a.nombre.strip().lower())
            if clave in vistos:
                raise ValueError(f"Ambiente repetido en el nivel {a.nivel}: {a.nombre}")
            vistos.add(clave)
        return v


class ParametrosMotor(BaseModel):
    """Parámetros configurables del motor. Todos se declaran como supuestos en la ficha."""

    ancho_pasillo_m: float = 1.5
    ancho_pasillo_lateral_m: float = 1.2
    escalera_ancho_m: float = 2.6
    escalera_largo_m: float = 3.8
    patio_area_objetivo_m2: float = 12.0
    muro_exterior_m: float = 0.25
    muro_interior_m: float = 0.15
    losa_m: float = 0.20
    tolerancia_programa: float = 0.15
    dim_minima_m: dict[str, float] = Field(
        default_factory=lambda: {"publico": 2.0, "privado": 2.0, "servicio": 1.2}
    )
    area_por_defecto_m2: dict[str, float] = Field(
        default_factory=lambda: {"publico": 40.0, "privado": 15.0, "servicio": 8.0}
    )


# ---------------------------------------------------------------- salida

Punto = tuple[float, float]


class Espacio(BaseModel):
    id: str
    nombre: str
    funcion: Literal["publico", "privado", "servicio", "circulacion", "escalera", "patio"]
    poligono: list[Punto]
    area_m2: float
    ancho_m: float
    largo_m: float
    area_objetivo_m2: Optional[float] = None
    luz_natural: bool = False
    acceso_directo: bool = False
    acceso_desde: Optional[str] = None


class Muro(BaseModel):
    id: str
    a: Punto
    b: Punto
    espesor_m: float
    altura_m: float
    exterior: bool
    material: str
    espacios: list[str] = Field(default_factory=list)
    # tramos sólidos a lo largo del muro para el 3D: (s0, s1, z0, z1) relativos
    piezas: list[tuple[float, float, float, float]] = Field(default_factory=list)


class Vano(BaseModel):
    id: str
    tipo: Literal["puerta", "ventana"]
    nombre: str
    muro_id: str
    centro: Punto
    ancho_m: float
    alto_m: float
    alfeizar_m: float
    entre: list[str] = Field(default_factory=list)


class Losa(BaseModel):
    id: str
    nombre: str
    poligono: list[Punto]
    vacios: list[list[Punto]] = Field(default_factory=list)
    espesor_m: float
    cota_m: float
    area_m2: float


class Peldano(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float
    z1: float


class Escalera(BaseModel):
    id: str
    nivel_desde: int
    nivel_hasta: int
    huella: list[Punto]
    peldanos: list[Peldano]
    contrapaso_m: float
    paso_m: float
    numero_contrapasos: int


class Nivel(BaseModel):
    numero: int
    nombre: str
    cota_m: float
    altura_m: float
    espacios: list[Espacio]
    muros: list[Muro]
    vanos: list[Vano]
    losas: list[Losa]
    escaleras: list[Escalera] = Field(default_factory=list)


class Verificacion(BaseModel):
    id: str
    titulo: str
    estado: EstadoVerificacion
    detalle: str
    evidencia: list[str] = Field(default_factory=list)
    fuente: Optional[str] = None


class Alternativa(BaseModel):
    id: str
    nombre: str
    estrategia: str
    descripcion: str
    huella: str
    motor_version: str
    tiempo_ms: float
    terreno: list[Punto]
    niveles: list[Nivel]
    indicadores: dict[str, float | int | bool | str]
    verificaciones: list[Verificacion]
    supuestos: list[str]
