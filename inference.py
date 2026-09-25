"""Gemini multimodal com validação local e diagnóstico sem divulgar evidências.

- Schema do provedor quando suportado; fallback sem schema somente em HTTP 400
  explicitamente relacionado a schema.
- Um único retry opcional, no mesmo modelo e com a mesma evidência, caso a
  resposta do modelo esteja incompleta ou estruturalmente inválida.
- Falhas por bloqueio/safety não são repetidas automaticamente nem convertidas
  em parecer sintético.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError
from schemas import GeminiAnalysis
from prompts import SYSTEM_INSTRUCTION, make_user_prompt

LOGGER = logging.getLogger('cyberrisk.inference')

GEMINI_OUTPUT_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'desenho': {'type': 'OBJECT', 'properties': {
            'classificacao': {'type': 'STRING', 'enum': ['ADEQUADO', 'PARCIAL', 'INADEQUADO', 'INSUFICIENTE']},
            'justificativa': {'type': 'STRING'}}, 'required': ['classificacao', 'justificativa']},
        'implementacao': {'type': 'OBJECT', 'properties': {
            'classificacao': {'type': 'STRING', 'enum': ['IMPLEMENTADO', 'PARCIAL', 'NÃO DEMONSTRADO']},
            'justificativa': {'type': 'STRING'}}, 'required': ['classificacao', 'justificativa']},
        'efetividade': {'type': 'OBJECT', 'properties': {
            'classificacao': {'type': 'STRING', 'enum': ['EFETIVO', 'PARCIAL', 'INEFETIVO', 'NÃO CONCLUSIVO']},
            'justificativa': {'type': 'STRING'}}, 'required': ['classificacao', 'justificativa']},
        'maturidade': {'type': 'OBJECT', 'properties': {
            'nivel': {'type': 'INTEGER', 'nullable': True},
            'justificativa': {'type': 'STRING'}}, 'required': ['nivel', 'justificativa']},
        'confianca_ia': {'type': 'STRING', 'enum': ['ALTA', 'MÉDIA', 'BAIXA']},
        'achados_observaveis': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'justificativa_analise': {'type': 'STRING'},
        'desvios_identificados': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'limitacoes_da_evidencia': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'sugestao_parecer': {'type': 'STRING'},
    },
    'required': ['desenho', 'implementacao', 'efetividade', 'maturidade',
                 'confianca_ia', 'achados_observaveis', 'justificativa_analise',
                 'desvios_identificados', 'limitacoes_da_evidencia', 'sugestao_parecer'],
}


# Nomes estruturais apenas, nunca valores capturados na evidência.
REQUIRED_KEYS = frozenset(GEMINI_OUTPUT_SCHEMA['required'])


class InvalidModelResponse(ValueError):
    """Indica apenas a categoria técnica, sem carregar conteúdo do usuário."""
    def __init__(self, reason: str, fields: tuple[str, ...] = ()):  # valores não são guardados
        self.reason = reason
        self.fields = fields
        super().__init__(reason)


def _schema_rejected(exc: Exception) -> bool:
    status = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
    try:
        if int(status) != 400:
            return False
    except (TypeError, ValueError):
        return False
    msg = str(exc).lower()  # inspecionado localmente, nunca registrado
    return any(term in msg for term in (
        'response_schema', 'responsejsonschema', 'response_json_schema',
        'additionalproperties', 'additional_properties', 'schema',
        'propertyordering', 'property_ordering',
    ))


def _service_unavailable(exc: Exception) -> bool:
    status = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
    try:
        return int(status) in (503, 504)
    except (TypeError, ValueError):
        return False


def _finish_reason(response: Any) -> str:
    try:
        candidates = getattr(response, 'candidates', None) or []
        reason = getattr(candidates[0], 'finish_reason', None) if candidates else None
        if reason is None:
            return ''
        # O SDK pode usar enum, inteiro, str ou None.
        return str(getattr(reason, 'name', reason)).upper()
    except (AttributeError, IndexError, TypeError):
        return ''


def _validate_object(value: Any) -> GeminiAnalysis:
    if isinstance(value, GeminiAnalysis):
        return value
    if not isinstance(value, dict):
        raise InvalidModelResponse('SCHEMA_INCOMPATIVEL')
    missing = REQUIRED_KEYS.difference(value)
    if missing:
        raise InvalidModelResponse('CAMPOS_AUSENTES', tuple(sorted(missing)))
    try:
        return GeminiAnalysis.model_validate(value)
    except ValidationError as exc:
        fields = tuple(sorted({
            str(err['loc'][0]) for err in exc.errors() if err.get('loc')
            and str(err['loc'][0]) in REQUIRED_KEYS
        }))
        raise InvalidModelResponse('CAMPOS_INVALIDOS', fields) from None


def _parse_analysis(response: Any) -> GeminiAnalysis:
    reason = _finish_reason(response)
    if 'MAX_TOKENS' in reason:
        raise InvalidModelResponse('RESPOSTA_TRUNCADA')
    if any(block in reason for block in ('SAFETY', 'BLOCKLIST', 'PROHIBITED', 'SPII', 'RECITATION')):
        raise InvalidModelResponse('RESPOSTA_BLOQUEADA')
    parsed = getattr(response, 'parsed', None)
    if parsed is not None:
        if hasattr(parsed, 'model_dump'):
            parsed = parsed.model_dump()
        return _validate_object(parsed)
    try:
        raw_text = getattr(response, 'text', None)
    except (ValueError, AttributeError):
        raw_text = None
    if not raw_text or not isinstance(raw_text, str):
        raise InvalidModelResponse('RESPOSTA_VAZIA')
    text = raw_text.strip().lstrip('\ufeff').strip()
    # Só remove a cerca se TODO o conteúdo estiver no mesmo bloco JSON.
    match = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', text, flags=re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise InvalidModelResponse('JSON_INVALIDO') from None
    return _validate_object(value)


# Não inclua respostas anteriores inválidas num novo prompt: elas podem carregar
# informação sensível e induzir a replicação do erro.
FORMAT_RETRY_GUIDANCE = (
    '\nIMPORTANTE: Retorne um ÚNICO objeto JSON completo, sem markdown, sem texto fora do JSON. '
    'Preencha todos os dez campos do schema, inclusive as justificativas dos quatro critérios; para listas sem elementos use []. '
    'Para achados_observaveis, registre pelo menos um achado visível; se não houver '
    'conteúdo suficiente, indique explicitamente a insuficiência observada e '
    'escolha NÃO CONCLUSIVO na efetividade, INSUFICIENTE no desenho e null no Tier quando apropriado. Seja conciso.'
)


class GeminiAnalyzer:
    def __init__(self, api_key: str, model: str, fallback_model: str = '', format_retry: bool = True):
        self.api_key = api_key
        self.model = model
        self.fallback_model = (fallback_model or '').strip()
        self.format_retry = format_retry
        self.last_model_used = model
        self.attempted_fallback = False

    def analyze(self, code: str, name: str, requirement: str, image: bytes, mime: str) -> GeminiAnalysis:
        if not self.api_key:
            raise RuntimeError('GOOGLE_API_KEY ausente')
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError('Dependência google-genai não instalada') from exc

        client = genai.Client(api_key=self.api_key)
        try:
            original_prompt = make_user_prompt(code, name, requirement)
            image_part = types.Part.from_bytes(data=image, mime_type=mime)
            config_args = {
                'system_instruction': SYSTEM_INSTRUCTION,
                'response_mime_type': 'application/json',
                'max_output_tokens': 8192,
            }
            schema_supported = True

            def request(model: str, user_prompt: str, token_budget: int = 8192):
                nonlocal schema_supported
                args = {**config_args, 'max_output_tokens': token_budget}
                if schema_supported:
                    try:
                        return client.models.generate_content(
                            model=model, contents=[user_prompt, image_part],
                            config=types.GenerateContentConfig(**args, response_schema=GEMINI_OUTPUT_SCHEMA),
                        )
                    except Exception as exc:
                        if not _schema_rejected(exc):
                            raise
                        schema_supported = False
                return client.models.generate_content(
                    model=model, contents=[user_prompt, image_part],
                    config=types.GenerateContentConfig(**args),
                )

            self.last_model_used = self.model
            self.attempted_fallback = False
            try:
                response = request(self.model, original_prompt)
            except Exception as primary_error:
                if (not self.fallback_model or self.fallback_model == self.model
                        or not _service_unavailable(primary_error)):
                    raise
                self.attempted_fallback = True
                self.last_model_used = self.fallback_model
                response = request(self.fallback_model, original_prompt)

            try:
                return _parse_analysis(response)
            except InvalidModelResponse as exc:
                LOGGER.warning('Formato Gemini codigo=%s modelo=%s campos=%s tentativa=1',
                               exc.reason, self.last_model_used, ','.join(exc.fields) or '-',)
                # Bloqueio de segurança não vira chamada extra. Evita insistir em
                # material potencialmente não permitido pelo provedor.
                if not self.format_retry or exc.reason == 'RESPOSTA_BLOQUEADA':
                    raise

            # Reenvia a evidência ORIGINAL, nunca um fragmento ou resposta inválida.
            # Retry de formato pode gerar outra chamada cobrada pelo Google.
            corrected = request(self.last_model_used, original_prompt + FORMAT_RETRY_GUIDANCE,
                                token_budget=12288)
            try:
                return _parse_analysis(corrected)
            except InvalidModelResponse as exc:
                LOGGER.warning('Formato Gemini codigo=%s modelo=%s campos=%s tentativa=2',
                               exc.reason, self.last_model_used, ','.join(exc.fields) or '-')
                raise
        finally:
            client.close()
