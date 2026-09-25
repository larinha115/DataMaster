"""Contratos explícitos das quatro dimensões independentes da avaliação."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

DesignStatus = Literal['ADEQUADO', 'PARCIAL', 'INADEQUADO', 'INSUFICIENTE']
ImplementationStatus = Literal['IMPLEMENTADO', 'PARCIAL', 'NÃO DEMONSTRADO']
EffectivenessStatus = Literal['EFETIVO', 'PARCIAL', 'INEFETIVO', 'NÃO CONCLUSIVO']
Confidence = Literal['ALTA', 'MÉDIA', 'BAIXA']

TIER = {
    1: ('Partial', 'Governança e gestão de riscos ad hoc, com baixa integração e aplicação inconsistente.'),
    2: ('Risk-Informed', 'Riscos considerados pela gestão, mas aplicação e padronização ainda variáveis.'),
    3: ('Repeatable', 'Práticas institucionalizadas, repetíveis e regularmente revistas, com responsabilidades claras.'),
    4: ('Adaptive', 'Gestão de riscos adaptativa, integrada e continuamente ajustada por métricas, incidentes e ameaças.'),
}

class AuditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    controle_id: str = Field(min_length=5, max_length=32)
    imagem_base64: str = Field(min_length=32)
    politica: str | None = Field(default=None, max_length=35000)

    @field_validator('controle_id')
    @classmethod
    def strip_code(cls, value: str) -> str:
        return value.strip()

class DesignAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    classificacao: DesignStatus
    justificativa: str = Field(min_length=15)

class ImplementationAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    classificacao: ImplementationStatus
    justificativa: str = Field(min_length=15)

class EffectivenessAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    classificacao: EffectivenessStatus
    justificativa: str = Field(min_length=15)

class TierAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nivel: int | None = Field(default=None, ge=1, le=4)
    justificativa: str = Field(min_length=15)

class GeminiAnalysis(BaseModel):
    """Schema solicitado ao Gemini e validado localmente."""
    model_config = ConfigDict(extra='forbid')
    desenho: DesignAssessment
    implementacao: ImplementationAssessment
    efetividade: EffectivenessAssessment
    maturidade: TierAssessment
    confianca_ia: Confidence
    achados_observaveis: list[str] = Field(min_length=1)
    justificativa_analise: str = Field(min_length=25)
    desvios_identificados: list[str]
    limitacoes_da_evidencia: list[str]
    sugestao_parecer: str = Field(min_length=25)

    @model_validator(mode='after')
    def guard_inconclusive(self):
        # Não inventar Tier quando a evidência declaradamente não permite aferi-lo.
        if self.maturidade.nivel is None and not self.limitacoes_da_evidencia:
            raise ValueError('Tier não determinado requer descrição das limitações da evidência')
        return self

class AuditResponse(GeminiAnalysis):
    id_controle: str
    nome_controle: str
    nome_tier: str | None
    descricao_tier: str | None
    revisao_humana_recomendada: bool
    origem_resultado: Literal['MODELO_IA'] = 'MODELO_IA'
    modelo: str
    versao_prompt: str
    versao_catalogo: str
    id_analise: str
