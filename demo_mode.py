"""Cenários fechados e fictícios para apresentação sem consumo do Gemini.

Este módulo NÃO avalia imagens: só retorna pareceres ilustrativos pré-cadastrados.
Não reutilizar estes resultados em benchmarks ou decisões reais de auditoria.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from config import ROOT
from schemas import AuditResponse

DATA_DIR = ROOT / 'data' / 'demo_scenarios'
IMAGE_DIR = DATA_DIR / 'images'


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str = Field(pattern=r'^DEMO-0[1-5]$', min_length=7, max_length=7)


class DemoResponse(AuditResponse):
    confianca_ia: str = Field(pattern='^NÃO APLICÁVEL$')
    origem_resultado: str = Field(pattern='^DEMONSTRACAO$')
    validacao_especialista: str = Field(pattern='^PENDENTE$')


@lru_cache(maxsize=1)
def demo_cases() -> dict[str, dict]:
    """Lê apenas o catálogo fictício empacotado; independente de .env e planilha."""
    content = json.loads((DATA_DIR / 'casos.json').read_text(encoding='utf-8'))
    result = {}
    for c in content:
        ident = c['id']
        if ident in result or ident not in {f'DEMO-0{i}' for i in range(1, 6)}:
            raise ValueError('Identificação de cenário de demonstração inválida ou duplicada.')
        name = c['arquivo_imagem']
        # O diretório é fixo e o arquivo também precisa ter nome igual ao ID.
        if name != f'{ident}.png' or not (IMAGE_DIR / name).is_file():
            raise ValueError(f'Imagem fictícia ausente ou inválida para {ident}.')
        validated = DemoResponse.model_validate(c['resultado'])
        if validated.id_controle != c['controle']['codigo']:
            raise ValueError('ID do resultado não corresponde ao controle de demonstração.')
        result[ident] = c
    if len(result) != 5:
        raise ValueError('É necessário empacotar exatamente cinco cenários fictícios.')
    return result


def list_scenarios() -> list[dict]:
    return [
        {
            'id': c['id'], 'titulo': c['titulo'], 'controle': c['controle'],
            'imagem_url': f"/api/demo/imagens/{c['id']}",
            'origem': 'CENARIO_FICTICIO_PRE_CADASTRADO',
        }
        for c in demo_cases().values()
    ]


def get_scenario(case_id: str) -> dict:
    c = demo_cases().get(case_id)
    if c is None:
        raise HTTPException(404, 'Cenário fictício não encontrado.')
    return c


def get_demo_image(case_id: str) -> Path:
    return IMAGE_DIR / get_scenario(case_id)['arquivo_imagem']


def canned_result(case_id: str) -> DemoResponse:
    return DemoResponse.model_validate(get_scenario(case_id)['resultado'])
