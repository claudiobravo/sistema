"""Configuración del bot, leída de variables de entorno o de un fichero `.env`."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Proveedor = Literal["anthropic", "gemini", "ollama"]


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Gateway de WhatsApp (Evolution API) ---
    evolution_base_url: str = "http://evolution-api:8080"
    evolution_api_key: str = ""
    evolution_instancia: str = "ventas"

    # --- Seguridad del webhook ---
    # El token viaja en la ruta: POST /webhook/<WEBHOOK_TOKEN>
    webhook_token: str = ""

    # --- Blindaje: solo se procesa lo que venga de estos chats ---
    grupo_ventas_jid: str = ""
    jids_extra_permitidos: str = ""  # separados por comas, para pruebas

    # --- LLM ---
    llm_proveedor: Proveedor = "anthropic"
    anthropic_api_key: str = ""
    modelo_texto: str = "claude-haiku-4-5"
    modelo_vision: str = "claude-sonnet-5"
    llm_max_tokens: int = 2000
    llm_timeout: float = 90.0
    # Envía el PDF entero al modelo (solo Anthropic) cuando no tiene capa de texto.
    # Si es False se rasteriza la página con pdf2image y se manda como imagen.
    pdf_nativo: bool = True

    # Gemini / Ollama (alternativas self-hosted o de bajo coste)
    gemini_api_key: str = ""
    gemini_modelo: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    ollama_base_url: str = "http://ollama:11434"
    ollama_modelo: str = "llama3.2-vision"

    # --- Almacenamiento ---
    db_path: str = "/datos/ventas.db"

    # --- Procesado de media ---
    max_media_mb: float = 20.0
    pdf_max_paginas: int = 2
    pdf_min_caracteres: int = 80  # menos que esto = etiqueta escaneada, va por visión
    pdf_dpi: int = 200

    # --- Comportamiento ---
    responder_en_grupo: bool = True
    responder_errores: bool = True
    comandos_activos: bool = True
    cola_max: int = 200
    zona_horaria: str = "Europe/Madrid"
    log_level: str = "INFO"

    @field_validator("evolution_base_url", "gemini_base_url", "ollama_base_url")
    @classmethod
    def _sin_barra_final(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def jids_permitidos(self) -> frozenset[str]:
        """Conjunto blindado de chats que el bot escucha. Vacío = no escucha nada."""
        crudos = [self.grupo_ventas_jid, *self.jids_extra_permitidos.split(",")]
        return frozenset(j.strip() for j in crudos if j and j.strip())

    @property
    def max_media_bytes(self) -> int:
        return int(self.max_media_mb * 1024 * 1024)

    def problemas(self) -> list[str]:
        """Errores de configuración que impiden arrancar con garantías."""
        fallos: list[str] = []
        if not self.evolution_api_key:
            fallos.append("EVOLUTION_API_KEY vacía")
        if not self.webhook_token:
            fallos.append("WEBHOOK_TOKEN vacío (el webhook quedaría abierto a cualquiera)")
        if not self.jids_permitidos:
            fallos.append("GRUPO_VENTAS_JID vacío (el bot no escucharía ningún chat)")
        if self.llm_proveedor == "anthropic" and not self.anthropic_api_key:
            fallos.append("ANTHROPIC_API_KEY vacía")
        if self.llm_proveedor == "gemini" and not self.gemini_api_key:
            fallos.append("GEMINI_API_KEY vacía")
        return fallos


@lru_cache
def obtener_ajustes() -> Ajustes:
    return Ajustes()
